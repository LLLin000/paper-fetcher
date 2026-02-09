"""PubMed/PMID utilities for converting PMID to DOI and fetching OA full text."""

import logging
import time
from dataclasses import dataclass

import requests

logger = logging.getLogger(__name__)

# NCBI E-utilities API endpoints
EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
EFETCH_URL = f"{EUTILS_BASE}/efetch.fcgi"
ESUMMARY_URL = f"{EUTILS_BASE}/esummary.fcgi"

# Europe PMC API for OA full text
EPMC_API = "https://www.ebi.ac.uk/europepmc/webservices/rest"


@dataclass
class PMCIDResult:
    """Result from Europe PMC OA lookup."""
    pmcid: str = ""
    doi: str = ""
    full_text_url: str = ""
    pdf_url: str = ""
    is_oa: bool = False


@dataclass
class PubMedArticle:
    """Full PubMed article metadata."""
    pmid: str = ""
    doi: str = ""
    title: str = ""
    authors: list = None
    journal: str = ""
    year: int = None
    abstract: str = ""
    publisher_url: str = ""
    is_oa: bool = False
    
    def __post_init__(self):
        if self.authors is None:
            self.authors = []


def pmid_to_doi(pmid: str, email: str = "paper-fetcher@example.com") -> str | None:
    """Convert a PubMed ID (PMID) to a DOI using NCBI E-utilities.

    Args:
        pmid: The PubMed ID (e.g., "38123456").
        email: Email for NCBI API (polite pool).

    Returns:
        DOI string or None if not found.
    """
    params = {
        "db": "pubmed",
        "id": pmid.strip(),
        "rettype": "xml",
        "retmode": "xml",
        "email": email,
    }

    try:
        resp = requests.get(EFETCH_URL, params=params, timeout=15)
        resp.raise_for_status()

        # Parse XML to find DOI in ArticleId
        xml_text = resp.text

        # Simple regex-based extraction (avoid full XML parsing dependency)
        import re
        doi_match = re.search(r'<ArticleId IdType="doi">([^<]+)</ArticleId>', xml_text)
        if doi_match:
            doi = doi_match.group(1).strip()
            logger.info("Found DOI for PMID %s: %s", pmid, doi)
            return doi

        logger.warning("No DOI found for PMID %s", pmid)
        return None

    except requests.RequestException as e:
        logger.error("Failed to fetch DOI for PMID %s: %s", pmid, e)
        return None


def get_pmc_full_text(pmid: str) -> PMCIDResult:
    """Check if a PMID has an Open Access version in PubMed Central (PMC).

    Uses Europe PMC API to find OA full text.

    Args:
        pmid: The PubMed ID.

    Returns:
        PMCIDResult with OA information.
    """
    result = PMCIDResult()

    try:
        # Search Europe PMC for the PMID
        search_url = f"{EPMC_API}/search"
        params = {
            "query": f"PMID:{pmid.strip()}",
            "format": "json",
            "pageSize": 1,
        }

        resp = requests.get(search_url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        results = data.get("resultList", {}).get("result", [])
        if not results:
            logger.info("No Europe PMC result for PMID %s", pmid)
            return result

        article = results[0]

        # Extract DOI
        result.doi = article.get("doi", "")

        # Check for Open Access
        isOpenAccess = article.get("isOpenAccess", "")
        result.is_oa = isOpenAccess == "Y"

        if result.is_oa:
            # Get PMC ID
            result.pmcid = article.get("pmcid", "")

            # Construct full text URL
            if result.pmcid:
                result.full_text_url = f"https://www.ncbi.nlm.nih.gov/pmc/articles/{result.pmcid}/"
                result.pdf_url = f"https://www.ncbi.nlm.nih.gov/pmc/articles/{result.pmcid}/pdf/"

        logger.info(
            "Europe PMC lookup for PMID %s: OA=%s, PMCID=%s",
            pmid, result.is_oa, result.pmcid
        )
        return result

    except requests.RequestException as e:
        logger.error("Europe PMC lookup failed for PMID %s: %s", pmid, e)
        return result


def fetch_pmc_full_text_xml(pmcid: str) -> str | None:
    """Fetch full text XML from PubMed Central.

    Args:
        pmcid: PMC ID (e.g., "PMC1234567").

    Returns:
        Full text XML string or None.
    """
    # Remove PMC prefix if present
    pmcid_clean = pmcid.replace("PMC", "")

    url = f"{EPMC_API}/{pmcid_clean}/fullTextXML"

    try:
        resp = requests.get(url, timeout=30)
        if resp.status_code == 200:
            return resp.text
        logger.warning("PMC full text not available for %s: %d", pmcid, resp.status_code)
        return None
    except requests.RequestException as e:
        logger.error("Failed to fetch PMC full text for %s: %s", pmcid, e)
        return None


def get_article_from_pmid(pmid: str) -> PubMedArticle | None:
    """Fetch complete article info from PubMed including publisher URL.
    
    Args:
        pmid: PubMed ID
        
    Returns:
        PubMedArticle with metadata including publisher URL
    """
    article = PubMedArticle(pmid=pmid)
    
    try:
        # Fetch from PubMed
        params = {
            "db": "pubmed",
            "id": pmid.strip(),
            "retmode": "xml",
            "rettype": "abstract",
        }
        
        resp = requests.get(EFETCH_URL, params=params, timeout=15)
        resp.raise_for_status()
        
        xml_text = resp.text
        
        # Extract DOI
        doi_match = re.search(r'<ArticleId IdType="doi">([^<]+)</ArticleId>', xml_text)
        if doi_match:
            article.doi = doi_match.group(1).strip()
        
        # Extract title
        title_match = re.search(r'<ArticleTitle>([^<]+)</ArticleTitle>', xml_text)
        if title_match:
            article.title = title_match.group(1).strip()
        
        # Extract journal
        journal_match = re.search(r'<Title>([^<]+)</Title>', xml_text)
        if journal_match:
            article.journal = journal_match.group(1).strip()
        
        # Extract year
        year_match = re.search(r'<Year>(\d{4})</Year>', xml_text)
        if year_match:
            article.year = int(year_match.group(1))
        
        # Extract abstract
        abstract_match = re.search(r'<AbstractText[^>]*>([^<]+)</AbstractText>', xml_text)
        if abstract_match:
            article.abstract = abstract_match.group(1).strip()
        
        # Extract authors
        authors = re.findall(r'<LastName>([^<]+)</LastName>[^<]*<ForeName>([^<]+)</ForeName>', xml_text)
        for last, first in authors:
            article.authors.append(f"{last} {first}")
        
        # Look for publisher URL in comments/corrections
        # PubMed often has the official URL in CommentsCorrections or similar
        url_match = re.search(r'<CommentsCorrections.*RefType="CommentOn".*<RefSource>.*?Available from:\s*([^<\s]+)', xml_text, re.DOTALL)
        if url_match:
            article.publisher_url = url_match.group(1).strip()
        
        logger.info("Fetched PubMed article %s: %s", pmid, article.title[:50] if article.title else "No title")
        return article
        
    except Exception as e:
        logger.error("Failed to fetch PubMed article %s: %s", pmid, e)
        return None


def parse_identifier(identifier: str) -> tuple[str, str]:
    """Parse an identifier to determine its type and normalized value.

    Args:
        identifier: DOI, PMID, PMCID, or URL.

    Returns:
        Tuple of (type, normalized_value) where type is one of:
        "doi", "pmid", "pmcid", "url", "unknown"
    """
    identifier = identifier.strip()

    # DOI patterns
    if identifier.startswith("10.") or identifier.startswith("doi:"):
        return ("doi", identifier.replace("doi:", "").replace("DOI:", "").strip())

    # DOI URL
    for prefix in ["https://doi.org/", "http://doi.org/", "https://dx.doi.org/"]:
        if identifier.lower().startswith(prefix):
            return ("doi", identifier[len(prefix):])

    # PMID patterns
    import re
    pmid_match = re.match(r"^(?:PMID:?\s*)(\d+)$", identifier, re.IGNORECASE)
    if pmid_match:
        return ("pmid", pmid_match.group(1))

    # Pure numeric PMID
    if re.match(r"^\d{7,8}$", identifier):  # PMIDs are typically 7-8 digits
        return ("pmid", identifier)

    # PMCID patterns
    pmcid_match = re.match(r"^(?:PMC)?(\d+)$", identifier, re.IGNORECASE)
    if identifier.upper().startswith("PMC"):
        return ("pmcid", identifier.upper())

    # URL
    if identifier.startswith("http://") or identifier.startswith("https://"):
        return ("url", identifier)

    return ("unknown", identifier)
