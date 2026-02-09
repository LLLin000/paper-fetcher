"""PubMed search using NCBI E-utilities API."""

import logging
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

import requests

logger = logging.getLogger(__name__)

EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


@dataclass
class PubMedResult:
    """A single search result from PubMed."""
    pmid: str = ""
    title: str = ""
    authors: list[str] = field(default_factory=list)
    abstract: str = ""
    journal: str = ""
    pub_date: str = ""
    doi: str = ""
    pmcid: str = ""
    keywords: list[str] = field(default_factory=list)


def search(
    query: str,
    limit: int = 20,
    email: str = "paper-fetcher@example.com",
    api_key: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[PubMedResult]:
    """Search PubMed for articles.

    Args:
        query: Search query string (supports PubMed syntax).
        limit: Maximum number of results.
        email: Email for NCBI API (required by ToS).
        api_key: NCBI API key for higher rate limits.
        date_from: Start date (YYYY/MM/DD).
        date_to: End date (YYYY/MM/DD).

    Returns:
        List of PubMedResult objects.
    """
    if date_from or date_to:
        from_date = date_from or "1900/01/01"
        to_date = date_to or "3000/12/31"
        query = f'{query} AND ("{from_date}"[Date - Publication] : "{to_date}"[Date - Publication])'

    search_params = {
        "db": "pubmed",
        "term": query,
        "retmax": limit,
        "retmode": "json",
        "usehistory": "y",
        "email": email,
    }
    if api_key:
        search_params["api_key"] = api_key

    try:
        search_resp = requests.get(
            f"{EUTILS_BASE}/esearch.fcgi",
            params=search_params,
            timeout=15
        )
        search_resp.raise_for_status()
        search_data = search_resp.json()

        id_list = search_data.get("esearchresult", {}).get("idlist", [])
        if not id_list:
            return []

        _rate_limit(api_key)
        return fetch_articles(id_list, email, api_key)

    except requests.RequestException as e:
        logger.error("PubMed search failed: %s", e)
        return []


def fetch_articles(
    pmids: list[str],
    email: str = "paper-fetcher@example.com",
    api_key: str | None = None,
) -> list[PubMedResult]:
    """Fetch detailed article information by PMIDs.

    Args:
        pmids: List of PubMed IDs.
        email: Email for NCBI API.
        api_key: NCBI API key.

    Returns:
        List of PubMedResult objects.
    """
    if not pmids:
        return []

    fetch_params = {
        "db": "pubmed",
        "id": ",".join(pmids),
        "retmode": "xml",
        "rettype": "abstract",
        "email": email,
    }
    if api_key:
        fetch_params["api_key"] = api_key

    try:
        fetch_resp = requests.get(
            f"{EUTILS_BASE}/efetch.fcgi",
            params=fetch_params,
            timeout=30
        )
        fetch_resp.raise_for_status()

        return _parse_pubmed_xml(fetch_resp.text)

    except requests.RequestException as e:
        logger.error("PubMed fetch failed: %s", e)
        return []


def _parse_pubmed_xml(xml_text: str) -> list[PubMedResult]:
    """Parse PubMed XML response into PubMedResult objects."""
    results = []

    try:
        root = ET.fromstring(xml_text)

        for article in root.findall(".//PubmedArticle"):
            result = PubMedResult()

            medline = article.find("MedlineCitation")
            if medline is None:
                continue

            pmid_elem = medline.find("PMID")
            if pmid_elem is not None:
                result.pmid = pmid_elem.text or ""

            article_elem = medline.find("Article")
            if article_elem is not None:
                title_elem = article_elem.find("ArticleTitle")
                if title_elem is not None:
                    result.title = title_elem.text or ""

                for author in article_elem.findall(".//Author"):
                    last = author.find("LastName")
                    fore = author.find("ForeName")
                    if last is not None:
                        name = last.text or ""
                        if fore is not None and fore.text:
                            name = f"{name}, {fore.text}"
                        result.authors.append(name)

                journal_elem = article_elem.find("Journal/Title")
                if journal_elem is not None:
                    result.journal = journal_elem.text or ""

                pub_date = article_elem.find("Journal/JournalIssue/PubDate")
                if pub_date is not None:
                    year = pub_date.find("Year")
                    month = pub_date.find("Month")
                    day = pub_date.find("Day")
                    parts = []
                    if year is not None and year.text:
                        parts.append(year.text)
                    if month is not None and month.text:
                        parts.append(month.text)
                    if day is not None and day.text:
                        parts.append(day.text)
                    result.pub_date = "-".join(parts)

                abstract_elem = article_elem.find("Abstract/AbstractText")
                if abstract_elem is not None:
                    result.abstract = abstract_elem.text or ""

                for eloc in article_elem.findall("ELocationID"):
                    if eloc.get("EIdType") == "doi" and eloc.text:
                        result.doi = eloc.text
                        break

            pubmed_data = article.find("PubmedData")
            if pubmed_data is not None:
                for art_id in pubmed_data.findall(".//ArticleId"):
                    if art_id.get("IdType") == "pmc" and art_id.text:
                        result.pmcid = art_id.text
                        break

            for keyword in medline.findall(".//Keyword"):
                if keyword.text:
                    result.keywords.append(keyword.text)

            results.append(result)

    except ET.ParseError as e:
        logger.error("Failed to parse PubMed XML: %s", e)

    return results


def get_full_text_url(pmid: str) -> str | None:
    """Check if full text is available in PubMed Central.

    Args:
        pmid: PubMed ID.

    Returns:
        PMC URL if available, None otherwise.
    """
    params = {
        "dbfrom": "pubmed",
        "db": "pmc",
        "id": pmid,
        "linkname": "pubmed_pmc",
        "retmode": "json",
    }

    try:
        resp = requests.get(
            f"{EUTILS_BASE}/elink.fcgi",
            params=params,
            timeout=15
        )
        resp.raise_for_status()
        data = resp.json()

        linksets = data.get("linksets", [])
        if linksets and linksets[0].get("linksetdbs"):
            links = linksets[0]["linksetdbs"][0].get("links", [])
            if links:
                pmcid = links[0]
                return f"https://www.ncbi.nlm.nih.gov/pmc/articles/PMC{pmcid}/"

    except (requests.RequestException, KeyError, IndexError) as e:
        logger.debug("Full text check failed for %s: %s", pmid, e)

    return None


def _rate_limit(api_key: str | None = None):
    """Apply rate limiting (3 req/s without key, 10 req/s with key)."""
    delay = 0.1 if api_key else 0.34
    time.sleep(delay)
