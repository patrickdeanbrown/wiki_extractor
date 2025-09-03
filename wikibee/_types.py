from __future__ import annotations

from typing import Dict, Optional, TypedDict


class SearchResult(TypedDict):
    """Structured search result returned by WikiClient.search_articles."""

    title: str
    description: str
    url: str


class PageProps(TypedDict, total=False):
    """Subset of pageprops we care about from the MediaWiki API."""

    disambiguation: str


class PageObject(TypedDict, total=False):
    """Single page object from the MediaWiki extracts query."""

    title: str
    extract: Optional[str]
    pageprops: PageProps


class QueryResult(TypedDict, total=False):
    pages: Dict[str, PageObject]


class ExtractsResponse(TypedDict, total=False):
    """Top-level structure for the extracts API response."""

    query: QueryResult
