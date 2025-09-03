from __future__ import annotations

from typing import List, Optional, cast
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from ._types import ExtractsResponse, SearchResult


def _make_session() -> requests.Session:
    s = requests.Session()
    retries = Retry(
        total=3,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET", "POST"}),
    )
    adapter = HTTPAdapter(max_retries=retries)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    s.headers.update(
        {"User-Agent": "wikibee/1.0 (https://github.com/patrickdeanbrown/wikibee)"}
    )
    return s


class WikiClient:
    """Encapsulate HTTP session and MediaWiki API interaction."""

    def __init__(self, session: Optional[requests.Session] = None):
        self._session = session or _make_session()

    @property
    def session(self) -> requests.Session:
        return self._session

    def fetch_page(
        self, url: str, title: str, lead: bool, timeout: int
    ) -> ExtractsResponse:
        parsed = urlparse(url)
        netloc = parsed.netloc or "en.wikipedia.org"
        api_url = f"{parsed.scheme}://{netloc}/w/api.php"
        params: dict[str, str | int] = {
            "action": "query",
            "prop": "extracts|pageprops",
            "format": "json",
            "explaintext": 1,
            "redirects": 1,
            "titles": title,
        }
        if lead:
            params["exintro"] = 1

        resp = self._session.get(api_url, params=params, timeout=timeout)
        resp.raise_for_status()
        return cast(ExtractsResponse, resp.json())

    def search_articles(
        self, query: str, limit: int = 10, timeout: int = 15
    ) -> List[SearchResult]:
        """Search for Wikipedia articles using OpenSearch API with fuzzy matching."""
        api_url = "https://en.wikipedia.org/w/api.php"
        params: dict[str, str | int] = {
            "action": "opensearch",
            "search": query,
            "limit": limit,
            "namespace": 0,
            "format": "json",
            "profile": "fuzzy",
        }

        resp = self._session.get(api_url, params=params, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()

        # OpenSearch returns [query, titles, descriptions, urls]
        if len(data) < 4:
            return []

        titles = data[1]
        descriptions = data[2]
        urls = data[3]

        # Combine into structured results
        results: List[SearchResult] = []
        for i, title in enumerate(titles):
            results.append(
                {
                    "title": title,
                    "description": descriptions[i] if i < len(descriptions) else "",
                    "url": (
                        urls[i]
                        if i < len(urls)
                        else f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}"
                    ),
                }
            )

        return results
