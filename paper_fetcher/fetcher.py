"""Core paper fetching logic."""

import hashlib
import json
import logging
import random
import re
import time
from pathlib import Path
from urllib.parse import urlparse

import requests

from .auth import ProxyAuth
from .config import Config
from .extractors import html_extractor, pdf_extractor
from .models import Paper
from .sources import arxiv, unpaywall
from .sources.pubmed import pmid_to_doi

logger = logging.getLogger(__name__)

DOI_PATTERN = re.compile(r"^10\.\d{4,9}/[^\s]+$")


class PaperFetcher:
    """Main class for fetching academic papers."""

    def __init__(self, config: Config | None = None):
        self.config = config or Config.load()
        self.config.ensure_dirs()
        self._auth: ProxyAuth | None = None
        self._last_request_time = 0.0

    @property
    def auth(self) -> ProxyAuth:
        if self._auth is None:
            self._auth = ProxyAuth(self.config)
        return self._auth

    def fetch(self, identifier: str, use_cache: bool = True) -> Paper:
        """Fetch a paper by DOI or URL.

        Args:
            identifier: DOI, article URL, or EZproxy URL.
            use_cache: Whether to check/use cached results.

        Returns:
            Paper object with extracted content.
        """
        doi = self._parse_doi(identifier)
        url = self._parse_url(identifier)

        # Check cache (skip if input was PMID - always resolve fresh)
        if use_cache and doi and not re.match(r"^\d{7,8}$", identifier.strip()):
            cached = self._load_cache(doi)
            if cached:
                logger.info("Loaded from cache: %s", doi)
                return cached

        paper = Paper(doi=doi or "", url=url or "")

        # Step 1: Try Open Access sources first (if we have a DOI)
        if doi:
            oa_paper = self._try_open_access(doi)
            if oa_paper and oa_paper.full_text:
                self._save_cache(oa_paper)
                return oa_paper
            # Even if OA didn't get full text, preserve metadata
            if oa_paper:
                paper = oa_paper

        # Step 2: Resolve DOI to URL if needed
        if doi and not url:
            url = self._resolve_doi(doi)
            paper.url = url or ""

        if not url:
            logger.error("Could not determine URL for: %s", identifier)
            return paper

        # Step 3: Fetch via EZproxy
        self._rate_limit()
        paper = self._fetch_via_ezproxy(url, paper)

        # Save to cache
        if paper.full_text and paper.doi:
            self._save_cache(paper)

        return paper

    def _try_open_access(self, doi: str) -> Paper | None:
        """Try to fetch paper from Open Access sources."""
        logger.info("Checking Unpaywall for OA version of %s...", doi)
        oa = unpaywall.check_oa(doi, email=self.config.email)

        paper = Paper(
            doi=doi,
            title=oa.title,
            authors=oa.authors or [],
            journal=oa.journal,
            year=oa.year,
        )

        if not oa.is_oa:
            logger.info("No OA version found for %s.", doi)
            return paper

        # Check if it's an arXiv paper
        arxiv_id = None
        if oa.source == "arxiv" or "arxiv" in (oa.pdf_url or "").lower():
            arxiv_id = arxiv.extract_arxiv_id(oa.pdf_url or oa.html_url or "")

        if arxiv_id:
            return self._fetch_arxiv(arxiv_id, paper)

        # Try direct OA PDF download
        if oa.pdf_url:
            logger.info("Downloading OA PDF: %s", oa.pdf_url)
            paper.source = "open_access"
            self._rate_limit()
            try:
                resp = requests.get(oa.pdf_url, timeout=60, stream=True)
                resp.raise_for_status()
                if "pdf" in resp.headers.get("content-type", "").lower():
                    pdf_bytes = resp.content
                    paper.full_text = pdf_extractor.extract_from_bytes(pdf_bytes)
                    paper.figures = pdf_extractor.extract_figures_from_text(paper.full_text) if hasattr(pdf_extractor, 'extract_figures_from_text') else []
                    # Save PDF
                    pdf_path = self._save_pdf(doi, pdf_bytes)
                    paper.pdf_path = str(pdf_path) if pdf_path else ""
                    return paper
            except requests.RequestException as e:
                logger.warning("Failed to download OA PDF: %s", e)

        # Try OA HTML
        if oa.html_url:
            logger.info("Fetching OA HTML: %s", oa.html_url)
            paper.source = "open_access"
            self._rate_limit()
            try:
                resp = requests.get(oa.html_url, timeout=30)
                resp.raise_for_status()
                extracted = html_extractor.extract(resp.text, oa.html_url)
                self._apply_extracted(paper, extracted)
                return paper
            except requests.RequestException as e:
                logger.warning("Failed to fetch OA HTML: %s", e)

        return paper

    def _fetch_arxiv(self, arxiv_id: str, paper: Paper) -> Paper:
        """Fetch paper from arXiv."""
        logger.info("Fetching from arXiv: %s", arxiv_id)
        paper.source = "arxiv"

        # Get metadata
        meta = arxiv.fetch_metadata(arxiv_id)
        if meta:
            paper.title = paper.title or meta.get("title", "")
            paper.authors = paper.authors or meta.get("authors", [])
            paper.abstract = meta.get("abstract", "")
            paper.year = paper.year or meta.get("year")
            paper.url = meta.get("url", "")

        # Download PDF
        pdf_path = Path(self.config.output_dir) / f"arxiv_{arxiv_id.replace('/', '_')}.pdf"
        if arxiv.download_pdf(arxiv_id, str(pdf_path)):
            paper.pdf_path = str(pdf_path)
            paper.full_text = pdf_extractor.extract_text(pdf_path)
            paper.figures = pdf_extractor.extract_figures(pdf_path)

        return paper

    def _fetch_via_ezproxy(self, url: str, paper: Paper) -> Paper:
        """Fetch paper through EZproxy authenticated session."""
        # Ensure we're authenticated
        if not self.auth.login():
            logger.error("EZproxy authentication failed.")
            return paper

        paper.source = "ezproxy"

        try:
            resp = self.auth.fetch(url)
            resp.raise_for_status()
        except requests.RequestException as e:
            logger.error("Failed to fetch via EZproxy: %s", e)
            return paper

        content_type = resp.headers.get("content-type", "").lower()

        # If response is PDF
        if "pdf" in content_type:
            pdf_bytes = resp.content
            paper.full_text = pdf_extractor.extract_from_bytes(pdf_bytes)
            pdf_path = self._save_pdf(paper.doi or "unknown", pdf_bytes)
            paper.pdf_path = str(pdf_path) if pdf_path else ""
            return paper

        # HTML response - extract content
        extracted = html_extractor.extract(resp.text, resp.url)
        self._apply_extracted(paper, extracted)

        # Always try to find and download PDF for local storage
        pdf_url = self._find_pdf_link(resp.text, resp.url)
        if pdf_url:
            logger.info("Found PDF link, downloading: %s", pdf_url)
            self._rate_limit()
            try:
                pdf_resp = self.auth.fetch(pdf_url)
                pdf_resp.raise_for_status()
                if "pdf" in pdf_resp.headers.get("content-type", "").lower():
                    pdf_bytes = pdf_resp.content
                    pdf_path = self._save_pdf(paper.doi or "unknown", pdf_bytes)
                    paper.pdf_path = str(pdf_path) if pdf_path else ""
                    # If HTML extraction was poor, use PDF text instead
                    if not paper.full_text or len(paper.full_text) < 500:
                        paper.full_text = pdf_extractor.extract_from_bytes(pdf_bytes)
            except requests.RequestException as e:
                logger.warning("Failed to download PDF: %s", e)

        return paper

    def _apply_extracted(self, paper: Paper, extracted: dict):
        """Apply extracted content to a Paper object."""
        paper.title = paper.title or extracted.get("title", "")
        paper.authors = paper.authors or extracted.get("authors", [])
        paper.abstract = paper.abstract or extracted.get("abstract", "")
        paper.full_text = extracted.get("full_text", "")
        paper.figures = extracted.get("figures", [])
        paper.references = extracted.get("references", [])

    def _find_pdf_link(self, html: str, base_url: str) -> str | None:
        """Find a PDF download link in an HTML page."""
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "lxml")
        parsed = urlparse(base_url)
        base = f"{parsed.scheme}://{parsed.netloc}"

        # Common PDF link patterns
        for a in soup.find_all("a", href=True):
            href = a["href"]
            text = a.get_text(strip=True).lower()
            classes = " ".join(a.get("class", []))

            if any(kw in text for kw in ["pdf", "download pdf", "full text pdf"]):
                return self._resolve_url(href, base)
            if any(kw in classes for kw in ["pdf", "download-pdf"]):
                return self._resolve_url(href, base)
            if href.endswith(".pdf"):
                return self._resolve_url(href, base)

        return None

    def _resolve_url(self, href: str, base: str) -> str:
        """Resolve a relative URL against a base."""
        if href.startswith("http"):
            return href
        if href.startswith("//"):
            return "https:" + href
        if href.startswith("/"):
            return base + href
        return base + "/" + href

    def _parse_doi(self, identifier: str) -> str | None:
        """Extract DOI from identifier (handles DOI, PMID, PMCID)."""
        identifier = identifier.strip()

        # Direct DOI
        if DOI_PATTERN.match(identifier):
            return identifier

        # DOI URL
        for prefix in ["https://doi.org/", "http://doi.org/", "https://dx.doi.org/"]:
            if identifier.lower().startswith(prefix):
                return identifier[len(prefix):]

        # Try to extract DOI from URL path
        doi_match = re.search(r"(10\.\d{4,9}/[^\s&?#]+)", identifier)
        if doi_match:
            return doi_match.group(1)

        # Check for PMID (numeric 7-8 digits)
        if re.match(r"^\d{7,8}$", identifier):
            logger.info("Detected PMID: %s, converting to DOI...", identifier)
            doi = pmid_to_doi(identifier, email=self.config.email)
            if doi:
                logger.info("PMID %s -> DOI %s", identifier, doi)
                return doi
            else:
                logger.warning("Could not convert PMID %s to DOI", identifier)

        # Check for PMCID
        pmc_match = re.match(r"^PMC(\d+)$", identifier, re.IGNORECASE)
        if pmc_match:
            logger.info("Detected PMCID: %s", identifier)
            # For PMCID, we need special handling
            # Return a special marker that will be handled separately
            return None

        return None

    def _parse_url(self, identifier: str) -> str | None:
        """Extract URL from identifier."""
        identifier = identifier.strip()
        if identifier.startswith("http"):
            return identifier
        if DOI_PATTERN.match(identifier):
            return None  # Pure DOI, not a URL
        
        # Check for PMID - we will resolve via DOI later, not direct PubMed URL
        if re.match(r"^\d{7,8}$", identifier):
            return None  # Will be handled via DOI resolution
        
        return None

    def _resolve_doi(self, doi: str) -> str | None:
        """Resolve a DOI to its target URL (publisher website)."""
        # Direct publisher URL construction for common prefixes
        # This avoids redirects to PubMed for non-OA articles
        if doi.startswith("10.1016/"):
            # Elsevier ScienceDirect
            article_id = doi.split("/")[-1].upper()
            return f"https://www.sciencedirect.com/science/article/pii/{article_id}"
        elif doi.startswith("10.1002/"):
            # Wiley
            return f"https://doi.org/{doi}"
        elif doi.startswith("10.1038/"):
            # Nature
            return f"https://doi.org/{doi}"
        
        # Fall back to doi.org resolution
        try:
            resp = requests.get(
                f"https://doi.org/{doi}",
                allow_redirects=True,
                timeout=10,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
            )
            if resp.status_code == 200:
                final_url = resp.url
                # Don't use PubMed URLs for WebVPN
                if "pubmed.ncbi.nlm.nih.gov" in final_url:
                    logger.warning("DOI resolved to PubMed, but article is not OA. Cannot fetch via WebVPN.")
                    return None
                return final_url
        except requests.RequestException as e:
            logger.warning("Failed to resolve DOI %s: %s", doi, e)
        return None

    def _rate_limit(self):
        """Apply rate limiting between requests."""
        elapsed = time.time() - self._last_request_time
        delay = random.uniform(self.config.request_delay_min, self.config.request_delay_max)
        if elapsed < delay:
            sleep_time = delay - elapsed
            logger.debug("Rate limiting: sleeping %.1fs", sleep_time)
            time.sleep(sleep_time)
        self._last_request_time = time.time()

    def _save_pdf(self, doi: str, pdf_bytes: bytes) -> Path | None:
        """Save PDF to output directory."""
        safe_name = re.sub(r"[^\w\-.]", "_", doi)
        pdf_path = Path(self.config.output_dir) / f"{safe_name}.pdf"
        try:
            pdf_path.parent.mkdir(parents=True, exist_ok=True)
            pdf_path.write_bytes(pdf_bytes)
            logger.info("Saved PDF to %s", pdf_path)
            return pdf_path
        except OSError as e:
            logger.error("Failed to save PDF: %s", e)
            return None

    def _cache_key(self, doi: str) -> Path:
        """Get cache file path for a DOI."""
        h = hashlib.md5(doi.encode()).hexdigest()
        return Path(self.config.cache_dir) / f"{h}.json"

    def _load_cache(self, doi: str) -> Paper | None:
        """Load a cached paper result."""
        path = self._cache_key(doi)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return Paper.from_json(data)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to load cache for %s: %s", doi, e)
            return None

    def _save_cache(self, paper: Paper):
        """Save paper result to cache."""
        if not paper.doi:
            return
        path = self._cache_key(paper.doi)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(paper.to_json(), encoding="utf-8")
        except OSError as e:
            logger.warning("Failed to save cache for %s: %s", paper.doi, e)

    def clear_cache(self):
        """Clear all cached results."""
        cache_dir = Path(self.config.cache_dir)
        if cache_dir.exists():
            for f in cache_dir.glob("*.json"):
                f.unlink()
            logger.info("Cache cleared.")

    def close(self):
        """Clean up resources."""
        if self._auth:
            self._auth.close()
