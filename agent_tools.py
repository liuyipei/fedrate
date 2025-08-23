# agent_tools.py
# Tools for the Fed Rate Research Crew

from langchain.tools import StructuredTool
from pydantic import BaseModel, Field
import requests
from duckduckgo_search import DDGS

# --- Web search (DuckDuckGo) ---
class DDGArgs(BaseModel):
    query: str = Field(..., description="The web search query.")

def ddg_search(query: str) -> str:
    """Return top 5 results as bullet points: title — url, then snippet."""
    results_txt = []
    with DDGS() as ddgs:
        for r in ddgs.text(query, max_results=5):
            title = r.get("title", "")
            href = r.get("href", "")
            body = r.get("body", "")
            results_txt.append(f"- {title} — {href}\n  {body}")
    return "\n".join(results_txt)

search = StructuredTool.from_function(
    name="duckduckgo_search",
    description="Search the web with DuckDuckGo and return the top snippets.",
    args_schema=DDGArgs,
    func=ddg_search,
    return_direct=False,
)

# --- Simple fetch (with basic safety) ---
class FetchArgs(BaseModel):
    url: str = Field(..., description="HTTP/HTTPS URL to fetch")

ALLOWED_HOSTS = {
    "www.federalreserve.gov", "www.cmegroup.com", "www.wsj.com",
    "www.bloomberg.com", "www.ft.com", "fred.stlouisfed.org",
    "www.bls.gov", "www.bea.gov"
}

def fetch_url(url: str) -> str:
    """Fetch up to first 20k chars of a page. Whitelists major macro sites."""
    from urllib.parse import urlparse
    host = urlparse(url).netloc
    if host and host not in ALLOWED_HOSTS:
        return f"Blocked host: {host}. Allowed: {sorted(ALLOWED_HOSTS)}"
    r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    text = r.text
    return text[:20000]

scraper = StructuredTool.from_function(
    name="fetch_url",
    description="Fetch raw HTML/text from a URL (first 20k chars).",
    args_schema=FetchArgs,
    func=fetch_url,
    return_direct=False,
)
