"""DOI prefix to publisher mapping."""

# Common DOI prefixes and their publisher URL patterns
# Format: prefix -> (publisher_name, url_template_or_function)
DOI_PREFIX_MAP = {
    # Elsevier
    "10.1016": ("Elsevier", lambda doi: f"https://www.sciencedirect.com/science/article/pii/{doi.split('/')[-1].upper()}"),
    "10.1006": ("Elsevier (Academic Press)", lambda doi: f"https://www.sciencedirect.com/science/article/pii/{doi.split('/')[-1].upper()}"),
    
    # Springer
    "10.1007": ("Springer", lambda doi: f"https://link.springer.com/article/{doi}"),
    "10.1038": ("Nature (Springer)", lambda doi: f"https://www.nature.com/articles/{doi.split('/')[-1]}"),
    "10.1186": ("BioMed Central (Springer)", lambda doi: f"https://link.springer.com/article/{doi}"),
    
    # Wiley
    "10.1002": ("Wiley", lambda doi: f"https://onlinelibrary.wiley.com/doi/{doi}"),
    
    # ACS
    "10.1021": ("ACS", lambda doi: f"https://pubs.acs.org/doi/{doi}"),
    
    # APS
    "10.1103": ("APS", lambda doi: f"https://journals.aps.org/{doi.split('/')[1].split('.')[0]}/abstract/{doi}"),
    
    # IEEE
    "10.1109": ("IEEE", lambda doi: f"https://doi.org/{doi}"),  # IEEE redirects properly
    
    # Oxford
    "10.1093": ("Oxford University Press", lambda doi: f"https://doi.org/{doi}"),
    
    # Cambridge
    "10.1017": ("Cambridge University Press", lambda doi: f"https://doi.org/{doi}"),
    
    # Science (AAAS)
    "10.1126": ("Science (AAAS)", lambda doi: f"https://www.science.org/doi/{doi}"),
    
    # PNAS
    "10.1073": ("PNAS", lambda doi: f"https://www.pnas.org/doi/{doi}"),
    
    # Cell Press
    "10.1016": ("Cell Press (Elsevier)", lambda doi: f"https://www.cell.com/action/showPdf?pii={doi.split('/')[-1].upper()}"),
    
    # Taylor & Francis
    "10.1080": ("Taylor & Francis", lambda doi: f"https://doi.org/{doi}"),
    
    # SAGE
    "10.1177": ("SAGE", lambda doi: f"https://journals.sagepub.com/doi/{doi}"),
    
    # Karger
    "10.1159": ("Karger", lambda doi: f"https://doi.org/{doi}"),
    
    # Thieme
    "10.1055": ("Thieme", lambda doi: f"https://doi.org/{doi}"),
    
    # BMJ
    "10.1136": ("BMJ", lambda doi: f"https://doi.org/{doi}"),
    
    # JAMA
    "10.1001": ("JAMA", lambda doi: f"https://jamanetwork.com/journals/jama/article-abstract/{doi.split('/')[-1]}"),
    
    # NEJM
    "10.1056": ("NEJM", lambda doi: f"https://www.nejm.org/doi/full/{doi}"),
    
    # Lancet
    "10.1016": ("Lancet (Elsevier)", lambda doi: f"https://doi.org/{doi}"),
}


def get_publisher_url(doi: str) -> tuple[str | None, str | None]:
    """Get publisher URL from DOI.
    
    Returns:
        Tuple of (publisher_name, url) or (None, None) if unknown
    """
    # Extract prefix (first part before /)
    prefix = doi.split('/')[0] if '/' in doi else doi
    
    # Try exact prefix match
    if prefix in DOI_PREFIX_MAP:
        publisher, url_builder = DOI_PREFIX_MAP[prefix]
        return publisher, url_builder(doi)
    
    # Try 4-digit prefix match (e.g., 10.1007 -> Springer)
    short_prefix = prefix[:7]  # 10.xxxx
    for full_prefix, (publisher, url_builder) in DOI_PREFIX_MAP.items():
        if full_prefix.startswith(short_prefix):
            return publisher, url_builder(doi)
    
    return None, None


def resolve_doi_to_url(doi: str) -> str | None:
    """Resolve DOI to publisher URL using multiple strategies.
    
    Priority:
    1. Known publisher mapping (fast, no network)
    2. doi.org resolution (fallback)
    
    Returns:
        Publisher URL or None
    """
    import requests
    import logging
    
    logger = logging.getLogger(__name__)
    
    # Strategy 1: Use known publisher mapping
    publisher, url = get_publisher_url(doi)
    if publisher and url:
        logger.info("DOI %s mapped to %s: %s", doi, publisher, url)
        return url
    
    # Strategy 2: Use doi.org resolution
    logger.info("Unknown DOI prefix for %s, trying doi.org...", doi)
    try:
        resp = requests.get(
            f"https://doi.org/{doi}",
            allow_redirects=True,
            timeout=10,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
        )
        if resp.status_code == 200:
            final_url = resp.url
            # Don't use PubMed for paywalled content
            if "pubmed.ncbi.nlm.nih.gov" in final_url:
                logger.warning("DOI resolved to PubMed (not OA), cannot fetch via WebVPN")
                return None
            return final_url
    except Exception as e:
        logger.warning("doi.org resolution failed: %s", e)
    
    return None
