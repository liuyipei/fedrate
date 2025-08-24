# serp_utils.py

class SerpRecorder:
    """
    Records SERP items to JSONL with:
      - per-query top-K selection,
      - global de-duplication by URL across the run,
      - optional run-level cap on total items recorded,
      - aggregated unique results for downstream context.
    """
    def __init__(self, top_k_per_query: int = 6, run_cap: int | None = 20):
        self.top_k_per_query = int(top_k_per_query)
        self.run_cap = int(run_cap) if run_cap is not None else None
        self._seen_urls: set[str] = set()
        self._total_recorded = 0
        self._agg_results: list[dict] = []  # unique results in the order recorded

    @property
    def total_recorded(self) -> int:
        return self._total_recorded

    @property
    def all_results(self) -> list[dict]:
        return self._agg_results

    def _can_record_more(self) -> bool:
        return self.run_cap is None or self._total_recorded < self.run_cap

    def record_query_results(self, results: list[dict], query: str) -> int:
        """
        Try to record up to top_k_per_query unique URLs for this query.
        If the top results overlap with previously recorded URLs,
        we scan deeper to still hit K when possible.
        Returns how many were recorded for this query.
        """
        from io_clients import record_source_jsonl  # local import to avoid cycles

        taken = 0
        rank_in_query = 0
        # single-pass scan: pick FIRST K unique + within run cap
        for item in results:
            url = (item.get("url") or "").strip()
            if not url:
                continue
            # skip if we've reached limits
            if taken >= self.top_k_per_query or not self._can_record_more():
                break
            # skip duplicates seen in prior queries
            if url in self._seen_urls:
                continue

            # unique → record it
            rank_in_query += 1
            provider = item.get("provider", "unknown")
            snippet = item.get("snippet", "")
            record_source_jsonl(
                claim=f"SERP:{query}",
                url=url,
                snippet=snippet,
                extra={
                    "provider": provider,
                    "source_kind": "SERP",
                    "query": query,
                    "rank_in_query": rank_in_query
                }
            )

            self._seen_urls.add(url)
            self._agg_results.append({
                "title": item.get("title") or "",
                "url": url,
                "snippet": snippet,
                "provider": provider,
            })
            taken += 1
            self._total_recorded += 1

        return taken

    # Convenience: build a short, readable context block for prompts
    def context_block(self, max_items: int = 8) -> str:
        lines = []
        for i, r in enumerate(self._agg_results[:max_items], start=1):
            lines.append(
                f"[{i}] {r.get('title') or '(no title)'}\n"
                f"URL: {r.get('url','')}\n"
                f"Snippet: {r.get('snippet','')}\n"
                f"Provider: {r.get('provider','unknown')}\n"
            )
        return "\n".join(lines) if lines else "(no sources)"
