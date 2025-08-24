# manual_agent_demo.py
from __future__ import annotations
"""


A trimmed, monitoring-first rewrite of your research workflow that wires in:
  - Structured JSON logging with a stable RUN_ID
  - Per-run manifest + artifacts
  - HTTP client with caching/retries (via io_clients.fetch)
  - LLM prompt/response snapshotting (via io_clients.save_llm_call)
  - Source/citation recorder (via io_clients.record_source_jsonl)
  - Deterministic date handling with FEDRATE_TODAY or --today

This keeps your three-agent shape (Macro Analyst → Fact Checker → Executive Writer)
but focuses on reproducibility/observability rather than perfect content.

Requires the companion files introduced earlier:
  - run_logging.py
  - io_clients.py


Usage examples:
  Start from federate/
  python3 manual_agent_demo.py --today 2025-08-23 --temperature 0 --seed 42

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
    RUN_ID,
    get_today,
)
from run_files import RunFiles
from io_clients import fetch, save_llm_call, record_source_jsonl, load_sources_jsonl, openrouter_chat


log = init_logging()
write_manifest()

# Create RunFiles instance
from run_logging import ART_DIR
RUN_FILES = RunFiles(RUN_ID, ART_DIR)

# ---- Model constants --------------------------------------------------------
ANALYST_MODEL   = "z-ai/glm-4.5-air:free"
FACTCHECK_MODEL = "moonshotai/kimi-k2:free"
WRITER_MODEL    = "openai/gpt-oss-20b:free"


# ---- Config -----------------------------------------------------------------
@dataclass
class CliConfig:
    today: str
    temperature: float
    top_p: float
    seed: Optional[int]
    cache_only: bool
    stub: bool


def parse_args() -> CliConfig:
    p = argparse.ArgumentParser(description="Fed policy research (monitoring-first)")
    p.add_argument("--today", default=None, help="Override today's date (YYYY-MM-DD)")
    p.add_argument("--temperature", type=float, default=float(os.getenv("FEDRATE_TEMPERATURE", 0)), help="LLM temperature")
    p.add_argument("--top_p", type=float, default=float(os.getenv("FEDRATE_TOP_P", 1.0)), help="LLM nucleus sampling")
    p.add_argument("--seed", type=int, default=os.getenv("FEDRATE_SEED"), nargs="?", help="LLM seed if supported")
    p.add_argument("--cache-only", action="store_true", help="Serve HTTP from cache if available (still writes cache on miss)")
    p.add_argument("--stub", action="store_true", help="Use stub responses instead of calling real models")
    args = p.parse_args()
    today = get_today(args.today)
    return CliConfig(
        today=today,
        temperature=args.temperature,
        top_p=args.top_p,
        seed=(int(args.seed) if args.seed is not None else None),
        cache_only=bool(args.cache_only),
        stub=args.stub,
    )


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
                    {
                        "title": it.get("title") or "",
                        "url": it.get("url") or "",
                        "snippet": (it.get("description") or "").replace("<strong>","").replace("</strong>",""),
                        "provider": "brave",
                    }
                    for it in body.get("web", {}).get("results", [])
                ]
            else:
                # still stub parse for DDG
                results = [{
                    "title": f"{query} (stub)",
                    "url": url + "?q=" + query,
                    "snippet": "Search stub",
                    "provider": "ddg",
                }]

            log.info(json.dumps({"event": "search_ok", "provider": provider, "q": query}))
            return results

        except Exception as e:
            log.warning(json.dumps({"event": "search_fail", "provider": provider, "q": query, "err": str(e)}))
            continue
    return []


# ---- Agent: Macro Analyst ---------------------------------------------------
TOP_SERP_PER_QUERY = 6  # tune as you like

def macro_analyst(cfg: CliConfig) -> Dict[str, Any]:
    with timed_span("MacroAnalyst"):
        q1 = f"Federal Reserve FOMC Jackson Hole meeting July 30, 2025"
        q2 = "Jerome Powell Fed funds rate July 30, 2025"
        from serp_utils import SerpRecorder
        # record up to K per query, but never exceed run_cap across all queries
        rec = SerpRecorder(top_k_per_query=TOP_SERP_PER_QUERY, run_cap=20)

        for query in (q1, q2):
            res = search_with_fallback(query, cfg)  # make sure each item has title/url/snippet/provider
            _ = rec.record_query_results(res, query=query)  # returns how many it recorded for this query

        results = rec.all_results  # unique results across queries (in the order recorded)

        # Build RAG prompt using exactly what we recorded
        ## sources_block = rec.context_block(max_items=8)
        # We should ideally use the SERP and scraping to populate the following. However, for the purposes of a demo,
        # Hard code this content for now.
        sources_block = """
- Today’s Date:
  - August 24, 2025

- Current Effective Fed Funds Range & Stance:
  - Target range: 4.25%–4.50%, held steady at the July 29–30 FOMC meeting (two dissents preferring a cut)  
    https://www.fedprimerate.com/fedfundsrate/federal_funds_rate_history.htm
  - Effective Federal Funds Rate: ~4.33% (Aug 21 daily)  
    https://fred.stlouisfed.org/series/DFF

- Market-Implied Path for Next 2–4 FOMC Meetings (CME FedWatch):
  - September: ~80% probability of a 25 bp cut  
    https://www.cmegroup.com/newsletters/infocus/2025/08/markets-slow-to-start-the-week.html
  - October: ~60% probability of a cut  
    https://www.cmegroup.com/newsletters/infocus/2025/08/equities-rebound-to-start-the-week0.html
  - December: ~53% probability of a third cut by year-end  
    https://www.cmegroup.com/newsletters/infocus/2025/08/equities-rebound-to-start-the-week0.html

- Key FOMC Messaging (Statement, Minutes, SEP, Dot Plot):
  - Statement (July 30): Held steady, inflation still elevated, data-dependent stance  
    https://timesofindia.indiatimes.com/business/international-business/powell-doesnt-bow-to-trump-pressure-us-fed-keeps-interest-rate-unchanged-heres-what-the-fomc-statement-said/articleshow/123003483.cms
  - Minutes: Majority saw inflation as bigger risk, two dissents for a cut  
    https://www.bloomberg.com/news/articles/2025-08-20/fed-minutes-show-majority-of-fomc-saw-inflation-as-greater-risk  
    https://www.wsj.com/economy/central-banking/fed-minutes-july-meeting-ec9ab128
  - SEP/Dot Plot (June 2025): Two 25 bp cuts projected in 2025, ~3.5–3.75% end-2026, long-run ~3%  
    https://www.bondsavvy.com/fixed-income-investments-blog/fed-dot-plot  
    https://www.fidelity.com/learning-center/trading-investing/federal-reserve-dot-plot

- Key Policy Drivers:
  - Inflation: Above 2%, tariff effects boosting goods prices  
    https://www.bloomberg.com/news/articles/2025-08-20/fed-minutes-show-majority-of-fomc-saw-inflation-as-greater-risk
  - Labor Market: Signs of weakening, though unemployment still low  
    https://www.bloomberg.com/news/articles/2025-08-20/fed-minutes-show-majority-of-fomc-saw-inflation-as-greater-risk
  - Growth: Slowed in 2025, Q2 bounce not sustained  
    https://www.kiplinger.com/newsg/live/july-fed-meeting-updates-and-commentary-2025  
    https://www.bondsavvy.com/fixed-income-investments-blog/fed-dot-plot
  - Financial Conditions: Tighter credit, resilient equities/households, tariff headwinds  
    (drawn from FOMC commentary and minutes)

- Consensus Views (Reputable Sources):
  - Barron’s: Markets expect September cut; Powell signaled dovish tilt  
    https://www.barrons.com/articles/fed-powell-rate-cuts-stock-market-jackson-hole-423f528d
  - Reuters Breakingviews: Powell opened door to September cut, but stressed data-dependence  
    https://www.reuters.com/commentary/breakingviews/powells-fed-finale-self-unraveling-consensus-2025-08-22
  - Wall Street Journal: Minutes show broad support for hold, inflation concerns dominate, markets eye September cut  
    https://www.wsj.com/economy/central-banking/fed-minutes-july-meeting-ec9ab128
        """
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a macro analyst. Use ONLY the sources provided under the 'Context' section. "
                    "Do NOT mention training data or knowledge cutoff. If the context is insufficient to answer, "
                    "respond with EXACTLY: INSUFFICIENT_SOURCES."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Task: Summarize the Federal Reserve's current policy stance as of {cfg.today}.\n\n"
                    "Output:\n"
                    "1) One-paragraph bottom line.\n"
                    "2) 3-5 bullet drivers (inflation, labor, growth, financial conditions).\n"
                    "3) Cite sources inline with [#] indices that match the Context list.\n\n"
                    "Context:\n"
                    f"{sources_block}"
                ),
            },
        ]
        # --- LLM client call goes here ---
        if cfg.stub:
            resp = {
                "id": "resp_macro_stub",
                "choices": [{"message": {"role": "assistant", "content": "Analyst notes (stub)."}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 0, "completion_tokens": 0},
            }
        else:
            resp = openrouter_chat(
                messages,
                model=ANALYST_MODEL,
                temperature=cfg.temperature,
                top_p=cfg.top_p,
                seed=cfg.seed,
                max_tokens=3000,
            )

        save_llm_call(
            run_id=RUN_ID,
            role="MacroAnalyst",
            provider="openrouter" if not cfg.stub else "stub",
            model=ANALYST_MODEL,
            messages=messages,
            response=resp,
            temperature=cfg.temperature,
            top_p=cfg.top_p,
            seed=cfg.seed,
        )

        # Extract text
        body = resp.get("body", resp)
        choices = body.get("choices", [])
        analyst_text = choices[0]["message"]["content"] if choices else "(no content)"

        macro_notes_path = RUN_FILES.macro_notes()
        macro_notes_path.write_text(analyst_text)
        log.info(json.dumps({"event":"artifact_saved","name":"macro.notes.md","path":str(macro_notes_path)}))
        return {"notes": analyst_text, "search": results}


# ---- Source utilities -------------------------------------------------------
def load_and_format_sources() -> str:
    """Load collected sources and format them for fact checking."""
    sources = load_sources_jsonl()
    if not sources:
        return "No sources collected."
    
    # Group sources by query for better organization
    sources_by_query = {}
    for source in sources:
        query = source.get("query", "Unknown query")
        if query not in sources_by_query:
            sources_by_query[query] = []
        sources_by_query[query].append(source)
    
    # Format sources as a structured block
    formatted_sources = []
    for query, query_sources in sources_by_query.items():
        formatted_sources.append(f"Search Query: {query}")
        for i, source in enumerate(query_sources, 1):
            formatted_sources.append(f"  [{i}] {source.get('title', 'No title')}")
            formatted_sources.append(f"      URL: {source.get('url', 'No URL')}")
            formatted_sources.append(f"      Snippet: {source.get('snippet', 'No snippet')[:200]}...")
        formatted_sources.append("")  # Blank line between queries
    
    return "\n".join(formatted_sources)

def assess_source_completeness(analyst_notes: str, sources: list) -> list:
    """Assess if sources are complete based on claims in analyst notes."""
    if not sources:
        return ["sources_missing"]
    
    # Simple heuristic: if we have sources and analyst notes, assume sources are sufficient
    # In a more sophisticated implementation, we would check if each claim in the notes
    # is supported by at least one source
    if len(sources) > 0 and len(analyst_notes.strip()) > 0:
        return []  # No flags if we have sources and content
    
    return ["sources_incomplete"]

# ---- Agent: Fact Checker ----------------------------------------------------
def fact_checker(cfg: CliConfig, analyst: Dict[str, Any]) -> Dict[str, Any]:
    with timed_span("FactChecker"):
        # Load and format collected sources
        sources_text = load_and_format_sources()
        
        # Create enhanced fact checker prompt with sources
        messages = [
            {
                "role": "system", 
                "content": (
                    "You are a meticulous fact checker. Your task is to validate the claims in the provided notes "
                    "against the collected sources. For each claim, indicate whether it is supported, contradicted, "
                    "or not found in the sources. Be thorough and precise."
                )
            },
            {
                "role": "user", 
                "content": (
                    f"Check these notes (as of {cfg.today}):\n\n{analyst['notes']}\n\n"
                    f"Collected sources:\n{sources_text}\n\n"
                    "Please validate each claim in the notes against the sources. For each claim:\n"
                    "1. State whether it is supported, contradicted, or not found in the sources\n"
                    "2. Reference which source(s) support or contradict each claim\n"
                    "3. Note any discrepancies or areas needing clarification"
                )
            }
        ]
        
        if cfg.stub:
            resp = {
                "id": "resp_fact_stub",
                "choices": [{"message": {"role": "assistant", "content": "Fact check (stub): sources validated."}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 0, "completion_tokens": 0},
            }
        else:
            resp = openrouter_chat(
                messages,
                model=FACTCHECK_MODEL,
                temperature=cfg.temperature,
                top_p=cfg.top_p,
                seed=cfg.seed,
                max_tokens=1200,  # Increased token limit for more detailed response
            )
        
        # Extract text
        body = resp.get("body", resp)
        choices = body.get("choices", [])
        fact_checker_text = choices[0]["message"]["content"] if choices else "(no content)"
        
        # Assess source completeness
        sources = load_sources_jsonl()
        flags = assess_source_completeness(analyst['notes'], sources)
        
        factcheck_path = RUN_FILES.factcheck()
        factcheck_path.write_text(json.dumps({"text": fact_checker_text, "flags": flags}, indent=2))
        log.info(json.dumps({"event":"artifact_saved","name":"factcheck.json","path":str(factcheck_path)}))
        return {"text": fact_checker_text, "flags": flags}


# ---- Agent: Executive Writer ------------------------------------------------
def executive_writer(cfg: CliConfig, analyst: Dict[str, Any], fact: Dict[str, Any]) -> str:
    from io_clients import openrouter_chat  # ensure it's imported

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

        if cfg.stub:
            resp = {
                "id": "resp_writer_stub",
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "content": (
                            f"**Federal Reserve Policy Brief – {cfg.today}**\n\n"
                            "Bottom Line: (stub) Confidence limited due to placeholder sources.\n\n"
                            "**Methodology & Limitations**\n"
                            "- Search providers used: brave, ddg (stubs)\n"
                            "- Placeholders present; results are not investment advice.\n"
                        )
                    },
                    "finish_reason": "stop"
                }],
                "usage": {"prompt_tokens": 0, "completion_tokens": 0},
            }
            provider_used = "stub"
        else:
            resp = openrouter_chat(
                messages,
                model=WRITER_MODEL,
                temperature=cfg.temperature,
                top_p=cfg.top_p,
                seed=cfg.seed,
                max_tokens=1200,
            )
            provider_used = "openrouter"

        # persist full I/O
        save_llm_call(
            run_id=RUN_ID,
            role="ExecutiveWriter",
            provider=provider_used,
            model=WRITER_MODEL,
            messages=messages,
            response=resp,
            temperature=cfg.temperature,
            top_p=cfg.top_p,
            seed=cfg.seed,
        )

        # extract assistant text safely (works for both stub and real responses)
        body = resp.get("body", resp)  # 'body' exists when coming from fetch(); else use resp directly
        choices = body.get("choices", [])
        brief_text = choices[0]["message"]["content"] if choices else "(no content)"

        brief_path = RUN_FILES.brief()
        brief_path.write_text(brief_text)
        log.info(json.dumps({"event":"artifact_saved","name":"brief.md","path":str(brief_path)}))
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
            sources_path = RUN_FILES.sources_raw()
            fact = fact_checker(cfg, analyst)
            brief = executive_writer(cfg, analyst, fact)
    except Exception as e:
        log.error(json.dumps({"event": "pipeline_failed", "err": str(e)}))
        return 1

    # Summarize debug info
    debug_info = {
        "search_results_found": sum(1 for _ in analyst.get("search", [])),
        "sources_file": str(RUN_FILES.sources_raw()),
        "errors": fact.get("flags", []),
    }
    debug_path = RUN_FILES.debug()
    debug_path.write_text(json.dumps(debug_info, indent=2))
    log.info(json.dumps({"event": "done", "run_id": RUN_ID, "artifacts": debug_info}))

    sources_list = load_sources_jsonl()
    sources_json_path = RUN_FILES.sources_raw()
    if sources_list or not sources_json_path.exists():
        sources_json_path.write_text(json.dumps(sources_list, indent=2))
        log.info(json.dumps({"event":"artifact_saved","name":"sources.raw.json","path":str(sources_json_path)}))

    debug_info = {
        "search_results_found": sum(1 for _ in analyst.get("search", [])),
        "sources_file_jsonl": str(RUN_FILES.sources_final()),
        "sources_file_json": str(sources_json_path),
        "errors": fact.get("flags", []),
    }
    debug_path = RUN_FILES.debug()
    debug_path.write_text(json.dumps(debug_info, indent=2))
    log.info(json.dumps({"event":"artifact_saved","name":"debug.json","path":str(debug_path)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
