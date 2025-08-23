from __future__ import annotations
"""
small_langgraph4.py

A trimmed, monitoring-first rewrite of your research workflow that wires in:
  - Structured JSON logging with a stable RUN_ID
  - Per-run manifest + artifacts
  - HTTP client with caching/retries (via io_clients.fetch)
  - LLM prompt/response snapshotting (via io_clients.save_llm_call)
  - Source/citation recorder (via io_clients.record_source)
  - Deterministic date handling with FEDRATE_TODAY or --today

This keeps your three-agent shape (Macro Analyst → Fact Checker → Executive Writer)
but focuses on reproducibility/observability rather than perfect content.

Requires the companion files introduced earlier:
  - run_logging.py
  - io_clients.py

Usage examples:
  FEDRATE_TODAY=2025-08-23 python small_langgraph4.py
  python small_langgraph4.py --today 2025-08-23 --temperature 0 --seed 42

Notes:
  - External APIs here are represented as simple calls to `fetch`. Replace the URLs
    and payloads with your real endpoints (Brave/DDG/OpenRouter/etc.).
  - All artifacts are written under runs/<RUN_ID>.*
"""

import os
import json
import time
import argparse
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

# ---- Monitoring & I/O hooks -------------------------------------------------
from run_logging import (
    init_logging,
    write_manifest,
    timed_span,
    ART_DIR,
    RUN_ID,
    save_artifact,
    get_today,
)
from io_clients import fetch, save_llm_call, record_source


log = init_logging()
write_manifest()

# ---- Config -----------------------------------------------------------------
@dataclass
class CliConfig:
    today: str
    temperature: float
    top_p: float
    seed: Optional[int]
    cache_only: bool


def parse_args() -> CliConfig:
    p = argparse.ArgumentParser(description="Fed policy research (monitoring-first)")
    p.add_argument("--today", default=None, help="Override today's date (YYYY-MM-DD)")
    p.add_argument("--temperature", type=float, default=float(os.getenv("FEDRATE_TEMPERATURE", 0)), help="LLM temperature")
    p.add_argument("--top_p", type=float, default=float(os.getenv("FEDRATE_TOP_P", 1.0)), help="LLM nucleus sampling")
    p.add_argument("--seed", type=int, default=os.getenv("FEDRATE_SEED"), nargs="?", help="LLM seed if supported")
    p.add_argument("--cache-only", action="store_true", help="Serve HTTP from cache if available (still writes cache on miss)")
    args = p.parse_args()
    today = get_today(args.today)
    return CliConfig(today=today, temperature=args.temperature, top_p=args.top_p, seed=(int(args.seed) if args.seed is not None else None), cache_only=bool(args.cache_only))


# ---- Environment / Tool checks ---------------------------------------------
def environment_check() -> None:
    log.info(json.dumps({"event": "env_check", "python": os.sys.version.split()[0]}))


def test_tool_availability(cfg: CliConfig) -> None:
    log.info("Testing tool availability...")
    # Example: hit a simple, harmless endpoint to verify HTTP works + cache
    try:
        r = fetch(
            "httpbin",
            "https://httpbin.org/get",
            params={"ping": "pong", "run": RUN_ID},
            use_cache=not cfg.cache_only,  # allow cache unless --cache-only explicitly requested
        )
        if isinstance(r.get("body"), dict):
            log.info("✅ HTTP client available")
        else:
            log.warning("HTTP client returned non-JSON body")
    except Exception as e:
        log.error(json.dumps({"event": "tool_test_failed", "tool": "httpbin", "err": str(e)}))


# ---- Search helpers ---------------------------------------------------------
def search_with_fallback(query: str, cfg: CliConfig) -> List[Dict[str, Any]]:
    """Minimal example search with provider rotation and caching.
    Replace URLs with your real search providers.
    """
    providers = [
        ("brave", "https://api.search.brave.com/res/v1/web/search"),  # Brave JSON API
        ("ddg",  "https://html.duckduckgo.com/html"),                 # DDG HTML endpoint
    ]

    headers = {"User-Agent": "Mozilla/5.0 (compatible; fedrate/1.0)"}

    for provider, url in providers:
        try:
            if provider == "brave":
                # Brave expects an API key in Authorization
                headers = {
                    "User-Agent": "fedrate/1.0",
                    "Accept": "application/json",
                    "X-Subscription-Token": os.getenv("BRAVE_API_KEY", "")
                }
                params = {"q": query, "count": 5}
            else:  # ddg
                headers = {"User-Agent": "Mozilla/5.0"}
                params = {"q": query}

            res = fetch(provider, url, params=params,
                        headers=headers,
                        use_cache=True,
                        cache_only=cfg.cache_only)

            body = res.get("body")
            if provider == "brave" and isinstance(body, dict):
                results = [
                    {"title": item.get("title"),
                    "url": item.get("url"),
                    "snippet": item.get("description")}
                    for item in body.get("web", {}).get("results", [])
                ]
            else:
                # still stub parse for DDG
                results = [{"title": f"{query} (stub)",
                            "url": url + "?q=" + query,
                            "snippet": "Search stub"}]

            log.info(json.dumps({"event": "search_ok", "provider": provider, "q": query}))
            return results

        except Exception as e:
            log.warning(json.dumps({"event": "search_fail", "provider": provider, "q": query, "err": str(e)}))
            continue
    return []


# ---- Agent: Macro Analyst ---------------------------------------------------
def macro_analyst(cfg: CliConfig) -> Dict[str, Any]:
    with timed_span("MacroAnalyst"):
        q1 = f"Federal Reserve FOMC meeting {cfg.today}"
        q2 = "Fed funds rate current"
        results = []
        results += search_with_fallback(q1, cfg)
        results += search_with_fallback(q2, cfg)

        # Record at least one source for provenance (stub)
        for r in results[:2]:
            record_source(claim=f"Search evidence for {cfg.today}", url=r["url"], snippet=r["snippet"])

        # Call LLM (pseudo) — replace with your client and pass through params
        messages = [
            {"role": "system", "content": "You are a macro analyst."},
            {"role": "user", "content": f"Summarize current Fed stance as of {cfg.today}."},
        ]
        # --- LLM client call goes here ---
        fake_response = {
            "id": "resp_macro_001",
            "choices": [{"message": {"role": "assistant", "content": "Analyst notes (stub)."}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 42, "completion_tokens": 17},
        }
        save_llm_call(
            run_id=RUN_ID,
            role="MacroAnalyst",
            provider="openrouter",
            model="z-ai/glm-4.5-air:free",
            messages=messages,
            response=fake_response,
            temperature=cfg.temperature,
            top_p=cfg.top_p,
            seed=cfg.seed,
        )

        analyst_text = fake_response["choices"][0]["message"]["content"]
        save_artifact("macro.notes.md", analyst_text)
        return {"notes": analyst_text, "search": results}


# ---- Agent: Fact Checker ----------------------------------------------------
def fact_checker(cfg: CliConfig, analyst: Dict[str, Any]) -> Dict[str, Any]:
    with timed_span("FactChecker"):
        messages = [
            {"role": "system", "content": "You are a meticulous fact checker."},
            {"role": "user", "content": f"Check these notes (as of {cfg.today}):\n\n{analyst['notes']}"},
        ]
        fake_response = {
            "id": "resp_fact_001",
            "choices": [{"message": {"role": "assistant", "content": "Fact check (stub): sources incomplete."}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 64, "completion_tokens": 12},
        }
        save_llm_call(
            run_id=RUN_ID,
            role="FactChecker",
            provider="openrouter",
            model="moonshotai/kimi-k2:free",
            messages=messages,
            response=fake_response,
            temperature=cfg.temperature,
            top_p=cfg.top_p,
            seed=cfg.seed,
        )
        text = fake_response["choices"][0]["message"]["content"]
        save_artifact("factcheck.json", {"text": text, "flags": ["sources_incomplete"]})
        return {"text": text, "flags": ["sources_incomplete"]}


# ---- Agent: Executive Writer ------------------------------------------------
def executive_writer(cfg: CliConfig, analyst: Dict[str, Any], fact: Dict[str, Any]) -> str:
    with timed_span("ExecutiveWriter"):
        messages = [
            {"role": "system", "content": "You write concise executive briefs with a methodology box."},
            {"role": "user", "content": json.dumps({
                "date": cfg.today,
                "analyst": analyst.get("notes"),
                "fact": fact.get("text"),
                "flags": fact.get("flags", []),
            })},
        ]
        fake_response = {
            "id": "resp_writer_001",
            "choices": [{"message": {"role": "assistant", "content": (
                f"""**Federal Reserve Policy Brief – {cfg.today}**\n\n"""
                "Bottom Line: (stub) Confidence limited due to placeholder sources.\n\n"
                "**Methodology & Limitations**\n- Search providers used: brave, ddg (stubs)\n- Placeholders present; results are not investment advice.\n"
            )}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 80, "completion_tokens": 40},
        }
        save_llm_call(
            run_id=RUN_ID,
            role="ExecutiveWriter",
            provider="openrouter",
            model="openai/gpt-oss-20b:free",
            messages=messages,
            response=fake_response,
            temperature=cfg.temperature,
            top_p=cfg.top_p,
            seed=cfg.seed,
        )
        brief_text = fake_response["choices"][0]["message"]["content"]
        save_artifact("brief.md", brief_text)
        return brief_text


# ---- Main -------------------------------------------------------------------
def main() -> int:
    cfg = parse_args()
    log.info(json.dumps({"event": "start", "run_id": RUN_ID, "today": cfg.today}))

    environment_check()
    test_tool_availability(cfg)

    try:
        with timed_span("Pipeline"):
            analyst = macro_analyst(cfg)
            sources_path = ART_DIR / f"{RUN_ID}.sources.json"
            fact = fact_checker(cfg, analyst)
            brief = executive_writer(cfg, analyst, fact)
    except Exception as e:
        log.error(json.dumps({"event": "pipeline_failed", "err": str(e)}))
        return 1

    # Summarize debug info
    debug_info = {
        "search_results_found": sum(1 for _ in analyst.get("search", [])),
        "sources_file": f"runs/{RUN_ID}.sources.json",
        "errors": fact.get("flags", []),
    }
    save_artifact("debug.json", debug_info)
    log.info(json.dumps({"event": "done", "run_id": RUN_ID, "artifacts": debug_info}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


