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
            "and enter it in the sidebar, or set GROQ_API_KEY as an environment/secrets variable."
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


def call_vision_model(
    api_key: str,
    system_prompt: str,
    user_prompt: str,
    images: List[Image.Image],
    model: Optional[str] = None,
    temperature: float = 0.1,
    max_tokens: int = 900,
) -> str:
    """Send text + one or more images to a Groq vision-capable model and
    return the raw text response (expected to be a JSON string, validated
    by the caller in ai/extraction.py).

    Reliability behaviour:
      - images are capped at config.MAX_IMAGES_PER_REQUEST (Groq rejects
        requests with more images than the model allows)
      - transient errors (429 / 5xx / connection) are retried with
        exponential backoff (config.GROQ_MAX_RETRIES)
      - if the model rejects the optional reasoning params, the call is
        retried once without them
      - if the primary model is unavailable/decommissioned (or keeps
        failing transiently), config.GROQ_VISION_MODEL_FALLBACK is tried
    """
    client = get_client(api_key)

    if len(images) > config.MAX_IMAGES_PER_REQUEST:
        logger.warning("Capping %d images to %d for the Groq request", len(images), config.MAX_IMAGES_PER_REQUEST)
        images = images[: config.MAX_IMAGES_PER_REQUEST]

    content = [{"type": "text", "text": user_prompt}]
    for img in images:
        content.append({"type": "image_url", "image_url": {"url": _image_to_data_url(img)}})
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": content},
    ]

    models = [model] if model else []
    for m in (config.GROQ_VISION_MODEL, config.GROQ_VISION_MODEL_FALLBACK):
        if m and m not in models:
            models.append(m)

    last_exc: Optional[Exception] = None
    for model_id in models:
        use_reasoning_params = True
        attempt = 0
        while True:
            kwargs = dict(
                model=model_id,
                temperature=temperature,
                max_tokens=max_tokens,
                messages=messages,
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
                if _is_transient(exc) and attempt < config.GROQ_MAX_RETRIES:
                    delay = config.GROQ_RETRY_BASE_DELAY_S * (2 ** attempt)
                    logger.warning("Transient Groq error on %s (%s); retrying in %.1fs", model_id, exc, delay)
                    time.sleep(delay)
                    attempt += 1
                    continue
                if _is_model_unavailable(exc) or _is_transient(exc):
                    logger.warning("Model %s failed (%s); trying fallback model if configured", model_id, exc)
                    break  # try the next model
                logger.exception("Groq vision call failed")
                raise GroqClientError(f"Groq API call failed: {exc}") from exc

    raise GroqClientError(f"Groq API call failed on all configured vision models: {last_exc}") from last_exc


def call_text_model(
    api_key: str,
    system_prompt: str,
    user_prompt: str,
    model: str = config.GROQ_TEXT_MODEL,
    temperature: float = 0.1,
    max_tokens: int = 1500,
    json_mode: bool = False,
) -> str:
    client = get_client(api_key)
    try:
        kwargs = dict(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        response = client.chat.completions.create(**kwargs)
        return response.choices[0].message.content
    except Exception as exc:
        logger.exception("Groq text call failed")
        raise GroqClientError(f"Groq API call failed: {exc}") from exc
