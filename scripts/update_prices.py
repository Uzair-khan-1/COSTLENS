"""
Weekly price update (run by GitHub Actions, or by hand):

    python scripts/update_prices.py                 # all live items, all cities
    python scripts/update_prices.py --cities Lahore --items CON-001 RBR-002

Keys come from environment variables: GROQ_API_KEY / GEMINI_API_KEY / OPENROUTER_API_KEY (AI reading, optional -
without them the agent reads prices with rules), TAVILY_API_KEY / BRAVE_API_KEY (optional search engines;
DuckDuckGo is used otherwise). Writes data/rates/ratebook.json, pending.json, history.json and a report
data/rates/last_update.md. Changes under 5 % from trusted sources are approved automatically; everything
else waits in pending.json for the admin page.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai.llm import LLMKeys  # noqa: E402
from pricing.agent import PriceAgent, default_search  # noqa: E402
from pricing.base_rates import CITIES, LIVE_ITEMS  # noqa: E402
from pricing.ratebook import RATES_DIR, RateBook  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cities", nargs="*", default=CITIES)
    ap.add_argument("--items", nargs="*", default=list(LIVE_ITEMS))
    ap.add_argument("--pause", type=float, default=1.5, help="seconds between page reads (be polite)")
    a = ap.parse_args()
    keys = LLMKeys(os.environ.get("GROQ_API_KEY", ""), os.environ.get("GEMINI_API_KEY", ""), os.environ.get("OPENROUTER_API_KEY", ""))
    agent = PriceAgent(RateBook(), keys=keys if keys.any() else None,
                       search=default_search(os.environ.get("TAVILY_API_KEY", ""), os.environ.get("BRAVE_API_KEY", "")),
                       pause_s=a.pause, log=lambda m: print("  " + m, flush=True))
    report = agent.run(cities=a.cities, items=a.items)
    (RATES_DIR / "last_update.md").write_text(report.markdown(), encoding="utf-8")
    print(report.summary())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
