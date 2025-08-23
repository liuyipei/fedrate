# io_clients.py
from __future__ import annotations
import os, json, time, hashlib, logging, random
from pathlib import Path
from typing import Any, Dict, Optional, Callable
import httpx

log = logging.getLogger("fedrate")

CACHE_DIR = Path(os.getenv("FEDRATE_CACHE_DIR", "cache"))
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# ------------------------- HTTP with cache & retries --------------------------

def _cache_key(provider: str, payload: dict) -> Path:
    h = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]
    return CACHE_DIR / f"{provider}-{h}.json"

def fetch(
    provider: str,
    url: str,
    method: str = "GET",
    *,
    params: dict | None = None,
    json_body: dict | None = None,
    headers: dict | None = None,
    use_cache: bool = True,
    cache_only: bool = False,
    max_retries: int = 4,
    timeout_s: float = 30.0,
) -> dict:
    payload = {"url": url, "method": method.upper(), "params": params or {}, "json": json_body or {}}
    key = _cache_key(provider, payload)

    # 1) cache-only path
    if cache_only:
        if key.exists():
            data = json.loads(key.read_text())
            log.info(json.dumps({"event":"http_cache_hit","provider":provider,"key":key.name,"mode":"cache_only"}))
            return data
        raise FileNotFoundError(f"cache_only: no cache for {provider} {url}")

    # 2) normal path with cache
    if use_cache and key.exists():
        data = json.loads(key.read_text())
        log.info(json.dumps({"event":"http_cache_hit","provider":provider,"key":key.name}))
        return data

    delay = 1.0
    for attempt in range(1, max_retries + 1):
        t0 = time.time()
        retryable_statuses = {408, 425, 429, 500, 502, 503, 504}
        try:
            with httpx.Client(timeout=timeout_s, follow_redirects=True) as c:
                r = c.request(method, url, params=params, json=json_body, headers=headers)
            meta = {"status": r.status_code, "ms": int((time.time() - t0) * 1000)}
            log.info(json.dumps({"event":"http_call","provider":provider,"meta":meta,"url":url}))
            if r.status_code in retryable_statuses:
                raise RuntimeError(f"retryable_status:{r.status_code}")
            r.raise_for_status()
            body: Any
            if "application/json" in r.headers.get("content-type", ""):
                body = r.json()
            else:
                body = r.text
            data = {"meta": meta, "body": body}
            key.write_text(json.dumps(data, indent=2))
            return data
        except Exception as e:
            log.warning(json.dumps({"event":"http_retry","provider":provider,"attempt":attempt,"err":str(e)}))
            if attempt == max_retries:
                raise
            time.sleep(delay + random.uniform(0, 0.5))
            delay *= 2

# ----------------------------- LLM I/O snapshot ------------------------------

def save_llm_call(
    run_id: str,
    role: str,
    provider: str,
    model: str,
    messages: list[dict],
    response: dict | str,
    **params,
) -> Path:
    """
    Persist a complete snapshot of an LLM call.
    """
    record = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "run_id": run_id,
        "role": role,
        "provider": provider,
        "model": model,
        "params": params,
        "messages": messages,
        "response": response,
    }
    from run_logging import ART_DIR, RUN_ID  # local import to avoid cycles
    p = ART_DIR / f"{RUN_ID}.{role}.{int(time.time())}.llm.json"
    p.write_text(json.dumps(record, indent=2))
    log.info(json.dumps({"event":"llm_saved","role":role,"path":str(p)}))
    return p

# --------------------------- Provenance helper -------------------------------

def record_source(claim: str, url: str, snippet: str, store_as: str = "sources.json") -> None:
    from run_logging import ART_DIR, RUN_ID
    p = ART_DIR / f"{RUN_ID}.{store_as}"
    items = []
    if p.exists():
        try:
            items = json.loads(p.read_text())
        except Exception:
            items = []
    items.append({
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "claim": claim, "url": url, "snippet": snippet
    })
    p.write_text(json.dumps(items, indent=2))
    log.info(json.dumps({"event":"source_recorded","url":url,"claim":claim[:80]}))
