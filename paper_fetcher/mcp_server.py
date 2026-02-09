"""Unified academic paper MCP server with multi-source search and full-text fetch.

Sources:
- PubMed (medical/biomedical)
- Google Scholar (general academic)
- Semantic Scholar (AI-powered search)
- arXiv (preprints)
- Unpaywall (Open Access)
"""

import logging
import sys

from mcp.server.fastmcp import FastMCP

from .config import Config
from .fetcher import PaperFetcher
from .sources import semantic_scholar
from .sources.pubmed_search import search as pubmed_search, get_full_text_url
from .sources.google_scholar import search as scholar_search, SCHOLARLY_AVAILABLE
from .sources.pubmed import pmid_to_doi, get_pmc_full_text, parse_identifier

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)

mcp = FastMCP("paper-fetcher")

_fetcher: PaperFetcher | None = None


def _get_fetcher() -> PaperFetcher:
    global _fetcher
    if _fetcher is None:
        _fetcher = PaperFetcher(Config.load())
    return _fetcher


# ==================== Search Tools ====================

@mcp.tool()
async def search_pubmed(
    query: str,
    limit: int = 20,
    year_from: int | None = None,
    year_to: int | None = None,
) -> str:
    """Search PubMed for medical/biomedical literature.

    Best for: Medical research, clinical studies, life sciences.

    Args:
        query: Search query (supports PubMed syntax, e.g., "TREM2 AND Alzheimer").
        limit: Maximum results (1-100, default 20).
        year_from: Start year filter.
        year_to: End year filter.
    """
    date_from = f"{year_from}/01/01" if year_from else None
    date_to = f"{year_to}/12/31" if year_to else None

    results = pubmed_search(
        query,
        limit=limit,
        date_from=date_from,
        date_to=date_to,
    )

    if not results:
        return "No results found."

    lines = [f"Found {len(results)} PubMed articles:\n"]
    for i, r in enumerate(results, 1):
        lines.append(f"### {i}. {r.title}")
        if r.authors:
            authors_str = ", ".join(r.authors[:3])
            if len(r.authors) > 3:
                authors_str += " et al."
            lines.append(f"- **Authors:** {authors_str}")
        if r.pub_date:
            lines.append(f"- **Date:** {r.pub_date}")
        if r.journal:
            lines.append(f"- **Journal:** {r.journal}")
        lines.append(f"- **PMID:** {r.pmid}")
        if r.doi:
            lines.append(f"- **DOI:** {r.doi}")
        if r.pmcid:
            lines.append(f"- **PMCID:** {r.pmcid} (Full text available)")
        if r.abstract:
            lines.append(f"- **Abstract:** {r.abstract[:200]}...")
        lines.append("")

    return "\n".join(lines)


@mcp.tool()
async def search_google_scholar(query: str, limit: int = 10) -> str:
    """Search Google Scholar for academic literature across all disciplines.

    Best for: Broad academic search, citations, finding related papers.

    Args:
        query: Search query.
        limit: Maximum results (1-20, default 10).
    """
    if not SCHOLARLY_AVAILABLE:
        return "Google Scholar search requires 'scholarly' package. Install with: pip install scholarly"

    results = scholar_search(query, limit=limit)

    if not results:
        return "No results found."

    lines = [f"Found {len(results)} Google Scholar articles:\n"]
    for i, r in enumerate(results, 1):
        lines.append(f"### {i}. {r.title}")
        if r.authors:
            lines.append(f"- **Authors:** {', '.join(r.authors[:3])}")
        if r.year:
            lines.append(f"- **Year:** {r.year}")
        lines.append(f"- **Citations:** {r.citations}")
        if r.url:
            lines.append(f"- **URL:** {r.url}")
        if r.abstract:
            lines.append(f"- **Abstract:** {r.abstract[:200]}...")
        lines.append("")

    return "\n".join(lines)


@mcp.tool()
async def search_semantic_scholar(
    query: str,
    limit: int = 10,
    year_range: str = "",
    fields_of_study: str = "",
) -> str:
    """Search Semantic Scholar for academic papers with AI-powered relevance.

    Best for: Computer science, AI/ML, finding highly-cited papers.

    Args:
        query: Search query.
        limit: Maximum results (1-100, default 10).
        year_range: Year filter (e.g., "2020-2024" or "2020-").
        fields_of_study: Comma-separated fields (e.g., "Medicine,Computer Science").
    """
    fields = [f.strip() for f in fields_of_study.split(",")] if fields_of_study else None

    results = semantic_scholar.search(
        query,
        limit=limit,
        year_range=year_range or None,
        fields_of_study=fields,
    )

    if not results:
        return "No results found."

    lines = [f"Found {len(results)} Semantic Scholar articles:\n"]
    for i, r in enumerate(results, 1):
        authors_str = ", ".join(r.authors[:3])
        if len(r.authors) > 3:
            authors_str += " et al."

        lines.append(f"### {i}. {r.title}")
        lines.append(f"- **Authors:** {authors_str}")
        if r.year:
            lines.append(f"- **Year:** {r.year}")
        if r.journal:
            lines.append(f"- **Journal:** {r.journal}")
        if r.doi:
            lines.append(f"- **DOI:** {r.doi}")
        elif r.arxiv_id:
            lines.append(f"- **arXiv:** {r.arxiv_id}")
        lines.append(f"- **Citations:** {r.citation_count}")
        if r.abstract:
            lines.append(f"- **Abstract:** {r.abstract[:200]}...")
        lines.append("")

    return "\n".join(lines)


# ==================== Fetch Tools ====================

@mcp.tool()
async def fetch_paper(identifier: str, format: str = "markdown") -> str:
    """Fetch full text of an academic paper by DOI, PMID, or URL.

    Automatically tries:
    1. Open Access sources (Unpaywall, PMC, arXiv)
    2. Institutional proxy (if configured)

    Args:
        identifier: DOI (10.xxx/xxx), PMID (12345678), or article URL.
        format: Output format - "markdown", "json", or "text".
    """
    id_type, id_value = parse_identifier(identifier)

    doi = None
    if id_type == "doi":
        doi = id_value
    elif id_type == "pmid":
        doi = pmid_to_doi(id_value)
        if not doi:
            pmc_result = get_pmc_full_text(id_value)
            if pmc_result.is_oa and pmc_result.full_text_url:
                return f"PMID {id_value} has Open Access full text at: {pmc_result.full_text_url}"
            return f"Could not find DOI for PMID {id_value}. Try searching PubMed first."

    fetch_identifier = doi or identifier
    fetcher = _get_fetcher()
    paper = fetcher.fetch(fetch_identifier)

    if not paper.full_text and not paper.abstract:
        return f"Could not extract full text for: {identifier}\nTitle: {paper.title}\nURL: {paper.url}"

    if format == "json":
        return paper.to_json()
    elif format == "text":
        return paper.to_text()
    else:
        return paper.to_markdown()


@mcp.tool()
async def get_paper_metadata(identifier: str) -> str:
    """Get metadata for a paper by DOI or PMID (no full text download).

    Args:
        identifier: DOI or PMID.
    """
    id_type, id_value = parse_identifier(identifier)

    doi = None
    if id_type == "doi":
        doi = id_value
    elif id_type == "pmid":
        doi = pmid_to_doi(id_value)
        if not doi:
            return f"Could not find DOI for PMID {id_value}"

    if not doi:
        return f"Could not parse identifier: {identifier}"

    result = semantic_scholar.get_paper(f"DOI:{doi}")
    if result is None:
        return f"Paper not found for: {identifier}"

    lines = [f"# {result.title}"]
    if result.authors:
        lines.append(f"**Authors:** {', '.join(result.authors)}")
    if result.year:
        lines.append(f"**Year:** {result.year}")
    if result.journal:
        lines.append(f"**Journal:** {result.journal}")
    lines.append(f"**DOI:** {result.doi}")
    if result.arxiv_id:
        lines.append(f"**arXiv:** {result.arxiv_id}")
    lines.append(f"**Citations:** {result.citation_count}")
    if result.abstract:
        lines.append(f"\n## Abstract\n\n{result.abstract}")

    return "\n".join(lines)


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
