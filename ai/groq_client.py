"""
Thin wrapper around the Groq Python SDK.

Kept separate from ai/extraction.py so the raw "call the model" mechanics
(retries, base64 encoding, model selection) are isolated from the
"parse this into our Pydantic schema" logic.
"""
from __future__ import annotations

import base64
import io
import logging
import time
from typing import List, Optional

from groq import Groq
from PIL import Image

import config

logger = logging.getLogger(__name__)


class GroqClientError(Exception):
    pass


def _image_to_data_url(image: Image.Image, max_dim: int = config.MAX_IMAGE_DIMENSION) -> str:
    img = image.convert("RGB")
    w, h = img.size
    longest = max(w, h)
    if longest > max_dim:
        scale = max_dim / longest
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    return f"data:image/jpeg;base64,{b64}"


def get_client(api_key: str) -> Groq:
    if not api_key:
        raise GroqClientError(
            "No Groq API key provided. Get a free key at https://console.groq.com/keys "
            "and set GROQ_API_KEY in Streamlit secrets (or as an environment variable)."
        )
    return Groq(api_key=api_key)


def _status_code(exc: Exception) -> Optional[int]:
    code = getattr(exc, "status_code", None)
    if code is None:
        code = getattr(getattr(exc, "response", None), "status_code", None)
    return code


def _is_transient(exc: Exception) -> bool:
    """429 rate limit, 5xx server errors and connection/timeout errors are
    worth retrying; 4xx request errors are not."""
    code = _status_code(exc)
    if code is not None:
        return code == 429 or code >= 500
    name = type(exc).__name__.lower()
    return "connection" in name or "timeout" in name


def _is_unsupported_param_error(exc: Exception) -> bool:
    """True when the model rejected the optional reasoning params (some
    models don't accept reasoning_effort/reasoning_format) - the call is
    then retried once without them."""
    return _status_code(exc) == 400 and "reasoning" in str(exc).lower()


def _is_model_unavailable(exc: Exception) -> bool:
    text = str(exc).lower()
    return _status_code(exc) in (400, 404) and (
        "model" in text and any(k in text for k in ("decommission", "deprecat", "not found", "does not exist", "not supported"))
    )


def _other_providers(keys, task: str):
    """(spec, client, model) for the non-Groq providers the user has keys for, in preference order."""
    from ai.llm import compat_client, provider_specs
    if keys is None:
        return []
    specs = provider_specs()
    out = []
    for name in ("gemini", "openrouter"):
        key = getattr(keys, name, "")
        if key:
            spec = specs[name]
            model = {"vision": spec.vision_model, "text": spec.text_model, "tools": spec.tool_model}[task]
            out.append((spec, compat_client(spec, key), model))
    return out


def call_vision_model(
    api_key: str,
    system_prompt: str,
    user_prompt: str,
    images: List[Image.Image],
    model: Optional[str] = None,
    temperature: float = 0.1,
    max_tokens: int = 900,
    keys=None,
) -> str:
    """Send text + one or more images to a vision-capable model and return the raw text response
    (expected to be a JSON string, validated by the caller).

    Free-tier behaviour (see ai/llm.py):
      - images are capped at config.MAX_IMAGES_PER_REQUEST and RESIZED / REDUCED so the request fits
        Groq's per-minute token budget (config.GROQ_REQUEST_TOKEN_BUDGET) - this prevents HTTP 413
        "Request too large ... ITPM" on the free tier
      - 413 -> shrink and retry; 429 with a short "try again in Xs" -> wait and retry; other transient
        errors -> exponential backoff (config.GROQ_MAX_RETRIES)
      - reasoning params rejected -> retried without them; model unavailable -> fallback model
      - if Groq still fails (or no Groq key) and `keys` has a Gemini / OpenRouter key, the request
        continues on those providers
    """
    from ai.llm import fit_images, is_overloaded, is_rate_limited, is_too_large, retry_after_seconds, send_with_retries, text_tokens

    if len(images) > config.MAX_IMAGES_PER_REQUEST:
        logger.warning("Capping %d images to %d for the request", len(images), config.MAX_IMAGES_PER_REQUEST)
        images = images[: config.MAX_IMAGES_PER_REQUEST]
    prompt_tok = text_tokens(system_prompt) + text_tokens(user_prompt) + 50
    last_exc: Optional[Exception] = None
    errors: List[str] = []

    if api_key:
        client = get_client(api_key)
        budget = int(getattr(config, "GROQ_REQUEST_TOKEN_BUDGET", 5500))
        models = [model] if model else []
        for m in (config.GROQ_VISION_MODEL, config.GROQ_VISION_MODEL_FALLBACK):
            if m and m not in models:
                models.append(m)
        for model_id in models:
            use_reasoning_params = True
            attempt = 0
            shrinks = 0
            waited = False
            model_budget = budget
            while True:
                imgs, _dim, note = fit_images(images, prompt_tok, model_budget, config.MAX_IMAGE_DIMENSION,
                                              config.MAX_IMAGES_PER_REQUEST)
                if note:
                    logger.info("Groq request fitted to the free-tier budget: %s", note)
                content = [{"type": "text", "text": user_prompt}]
                for img in imgs:
                    content.append({"type": "image_url", "image_url": {"url": _image_to_data_url(img)}})
                kwargs = dict(
                    model=model_id,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": content}],
                    response_format={"type": "json_object"},
                )
                if use_reasoning_params:
                    kwargs.update(reasoning_effort="none", reasoning_format="hidden")
                try:
                    response = client.chat.completions.create(**kwargs)
                    return response.choices[0].message.content
                except Exception as exc:  # noqa: BLE001 - SDK raises several types
                    last_exc = exc
                    if use_reasoning_params and _is_unsupported_param_error(exc):
                        logger.info("Model %s rejected reasoning params; retrying without them", model_id)
                        use_reasoning_params = False
                        continue
                    if is_too_large(exc) and shrinks < 2:
                        shrinks += 1
                        model_budget = int(model_budget * 0.6)
                        logger.warning("Request too large for %s; shrinking images and retrying", model_id)
                        continue
                    if is_rate_limited(exc) and not waited:
                        wait = retry_after_seconds(exc)
                        if wait is not None and wait <= 20:
                            logger.warning("Rate limited on %s; waiting %.1fs", model_id, wait)
                            time.sleep(wait + 0.5)
                            waited = True
                            continue
                    if _is_transient(exc) and attempt < config.GROQ_MAX_RETRIES:
                        delay = config.GROQ_RETRY_BASE_DELAY_S * (2 ** attempt)
                        logger.warning("Transient Groq error on %s (%s); retrying in %.1fs", model_id, exc, delay)
                        time.sleep(delay)
                        attempt += 1
                        continue
                    errors.append(f"Groq {model_id}: {_short(exc)}")
                    if _is_model_unavailable(exc) or _is_transient(exc) or is_too_large(exc):
                        logger.warning("Model %s failed (%s); trying the next model/provider", model_id, exc)
                        break
                    if not _other_providers(keys, "vision"):
                        logger.exception("Groq vision call failed")
                        raise GroqClientError("Groq API call failed - " + "; ".join(errors)) from exc
                    break

    for spec, client2, model2 in _other_providers(keys, "vision"):
        try:
            text, note = send_with_retries(client2, model2, system_prompt, user_prompt, images, spec.request_token_budget,
                                           spec.image_max_dim, max_tokens, json_mode=True, temperature=temperature)
            logger.info("Vision request answered by %s (%s) %s", spec.label, model2, note)
            return text
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            errors.append(f"{spec.label} {model2}: {_short(exc)}")
            logger.warning("%s failed: %s", spec.label, exc)
    if last_exc is None:
        raise GroqClientError("No AI key configured. Add GROQ_API_KEY or GEMINI_API_KEY in Streamlit secrets.")
    raise GroqClientError("AI call failed on all configured providers - " + "; ".join(errors)
                          + (" (the AI services are busy - please try again in a few minutes)" if is_overloaded(last_exc) else "")
                          ) from last_exc


def call_text_model(
    api_key: str,
    system_prompt: str,
    user_prompt: str,
    model: str = config.GROQ_TEXT_MODEL,
    temperature: float = 0.1,
    max_tokens: int = 1500,
    json_mode: bool = False,
    keys=None,
) -> str:
    from ai.llm import is_rate_limited, retry_after_seconds, send_with_retries

    last_exc: Optional[Exception] = None
    errors: List[str] = []
    if api_key:
        client = get_client(api_key)
        # the configured model first, then Groq's other free text models (models get retired from time to time)
        models = [model] + [m for m in GROQ_TEXT_FALLBACKS if m != model]
        for mdl in models:
            waited, use_json = False, json_mode
            while True:
                try:
                    kwargs = dict(model=mdl, temperature=temperature, max_tokens=max_tokens,
                                  messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}])
                    if use_json:
                        kwargs["response_format"] = {"type": "json_object"}
                    response = client.chat.completions.create(**kwargs)
                    return response.choices[0].message.content
                except Exception as exc:  # noqa: BLE001
                    last_exc = exc
                    wait = retry_after_seconds(exc)
                    if is_rate_limited(exc) and not waited and wait is not None and wait <= 20:
                        time.sleep(wait + 0.5)
                        waited = True
                        continue
                    if use_json and "response_format" in str(exc).lower() or (use_json and "json" in str(exc).lower()
                                                                                and "400" in str(exc)):
                        use_json = False  # this model does not support JSON mode - ask for plain JSON text
                        continue
                    errors.append(f"Groq {mdl}: {_short(exc)}")
                    break
            if not _model_problem(last_exc):
                break  # a key / quota / network problem - other Groq models won't help
        if not _other_providers(keys, "text"):
            logger.error("Groq text call failed: %s", "; ".join(errors))
            raise GroqClientError("Groq API call failed: " + "; ".join(errors)) from last_exc
    for spec, client2, model2 in _other_providers(keys, "text"):
        try:
            text, _note = send_with_retries(client2, model2, system_prompt, user_prompt, [], spec.request_token_budget,
                                            spec.image_max_dim, max_tokens, json_mode=json_mode, temperature=temperature)
            return text
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            errors.append(f"{spec.label} {model2}: {_short(exc)}")
    if last_exc is None:
        raise GroqClientError("No AI key configured. Add GROQ_API_KEY or GEMINI_API_KEY in Streamlit secrets.")
    raise GroqClientError("AI call failed on all configured providers - " + "; ".join(errors)) from last_exc


GROQ_TEXT_FALLBACKS = ["openai/gpt-oss-120b", "llama-3.3-70b-versatile", "openai/gpt-oss-20b", "llama-3.1-8b-instant"]


def _short(exc: Exception, n: int = 180) -> str:
    """One line: status code + the provider's own message (no JSON noise)."""
    import re as _re
    text = str(exc)
    m = _re.search(r"['\"]message['\"]\s*:\s*['\"]([^'\"]+)", text)
    msg = m.group(1) if m else text
    code = _re.search(r"Error code:\s*(\d{3})", text)
    return ((f"{code.group(1)} " if code else "") + _re.sub(r"\s+", " ", msg))[:n]


def _model_problem(exc: Optional[Exception]) -> bool:
    if exc is None:
        return False
    t = str(exc).lower()
    return any(k in t for k in ("404", "decommission", "no longer", "not found", "does not exist", "model_not_found",
                                "not supported", "invalid model"))


def check_ai_services(keys) -> List[dict]:
    """Tiny test request to every configured AI service (text, and image for the drawing check).
    -> [{"service", "model", "kind", "ok", "detail"}]"""
    from PIL import Image as _Image
    from ai.llm import provider_specs
    out: List[dict] = []
    img = _Image.new("RGB", (64, 64), "white")
    if getattr(keys, "groq", ""):
        client = get_client(keys.groq)
        for kind, models in (("text", [config.GROQ_TEXT_MODEL]),
                             ("image", [config.GROQ_VISION_MODEL, config.GROQ_VISION_MODEL_FALLBACK])):
            for mdl in models:
                content = "Reply with the single word OK."
                if kind == "image":
                    content = [{"type": "text", "text": "Reply with the single word OK."},
                               {"type": "image_url", "image_url": {"url": _image_to_data_url(img)}}]
                try:
                    client.chat.completions.create(model=mdl, max_tokens=5, temperature=0,
                                                   messages=[{"role": "user", "content": content}])
                    out.append({"service": "Groq", "model": mdl, "kind": kind, "ok": True, "detail": "working"})
                    break
                except Exception as exc:  # noqa: BLE001
                    out.append({"service": "Groq", "model": mdl, "kind": kind, "ok": False, "detail": _short(exc)})
    else:
        out.append({"service": "Groq", "model": "-", "kind": "-", "ok": False, "detail": "no GROQ_API_KEY in the secrets"})
    for name, key_attr in (("gemini", "gemini"), ("openrouter", "openrouter")):
        key = getattr(keys, key_attr, "")
        spec = provider_specs()[name]
        if not key:
            if name == "gemini":
                out.append({"service": spec.label, "model": "-", "kind": "-", "ok": False,
                            "detail": "no GEMINI_API_KEY in the secrets"})
            continue
        try:
            from ai.llm import OpenAICompatClient
            client = OpenAICompatClient(spec.base_url, key, timeout=30)
            client.chat.completions.create(model=spec.text_model, max_tokens=5, temperature=0,
                                           messages=[{"role": "user", "content": "Reply with the single word OK."}])
            out.append({"service": spec.label, "model": spec.text_model, "kind": "text + image", "ok": True, "detail": "working"})
        except Exception as exc:  # noqa: BLE001
            out.append({"service": spec.label, "model": spec.text_model, "kind": "text + image", "ok": False, "detail": _short(exc)})
    return out
