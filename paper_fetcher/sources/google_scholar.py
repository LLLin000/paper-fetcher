"""Google Scholar search using scholarly library."""

import logging
import time
from dataclasses import dataclass, field
from typing import Iterator

import requests

logger = logging.getLogger(__name__)

SCHOLARLY_AVAILABLE = False
try:
    from scholarly import scholarly, ProxyGenerator
    SCHOLARLY_AVAILABLE = True
except ImportError:
    logger.warning("scholarly library not installed. Install with: pip install scholarly")


@dataclass
class ScholarResult:
    """A single search result from Google Scholar."""
    title: str = ""
    authors: list[str] = field(default_factory=list)
    abstract: str = ""
    url: str = ""
    year: int | None = None
    citations: int = 0
    doi: str = ""


def search(
    query: str,
    limit: int = 10,
    use_proxy: bool = False,
) -> list[ScholarResult]:
    """Search Google Scholar for articles.

    Args:
        query: Search query string.
        limit: Maximum number of results.
        use_proxy: Whether to use a proxy (for rate limiting issues).

    Returns:
        List of ScholarResult objects.
    """
    if not SCHOLARLY_AVAILABLE:
        logger.error("scholarly library not installed")
        return []

    results = []

    try:
        if use_proxy:
            pg = ProxyGenerator()
            pg.FreeProxies()
            scholarly.use_proxy(pg)

        search_query = scholarly.search_pubs(query)

        for i, article in enumerate(search_query):
            if i >= limit:
                break

            bib = article.get("bib", {})

            result = ScholarResult(
                title=bib.get("title", ""),
                authors=bib.get("author", []),
                abstract=bib.get("abstract", ""),
                url=article.get("pub_url", "") or article.get("eprint_url", ""),
                year=bib.get("pub_year"),
                citations=article.get("num_citations", 0),
            )

            results.append(result)
            time.sleep(0.5)

        logger.info("Google Scholar found %d results for: %s", len(results), query)

    except Exception as e:
        logger.error("Google Scholar search failed: %s", e)

    return results


def get_author(author_name: str) -> dict | None:
    """Get author information from Google Scholar.

    Args:
        author_name: Name of the author to search for.

    Returns:
        Author information dict or None.
    """
    if not SCHOLARLY_AVAILABLE:
        return None

    try:
        search_query = scholarly.search_author(author_name)
        author = next(search_query, None)
        if author:
            scholarly.fill(author)
            return {
                "name": author.get("name", ""),
                "affiliation": author.get("affiliation", ""),
                "citations": author.get("citedby", 0),
                "h_index": author.get("hindex", 0),
                "interests": author.get("interests", []),
            }
    except Exception as e:
        logger.error("Failed to get author info: %s", e)

    return None
