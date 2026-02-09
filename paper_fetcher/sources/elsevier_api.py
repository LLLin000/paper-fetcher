"""Elsevier API client using elsapy for full text retrieval."""

import logging
import requests
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

ELSEVIER_API_BASE = "https://api.elsevier.com"


@dataclass
class ElsevierArticle:
    """Article data from Elsevier API."""
    doi: str = ""
    pii: str = ""
    title: str = ""
    authors: list = None
    abstract: str = ""
    full_text: str = ""
    journal: str = ""
    year: int = None
    pdf_url: str = ""
    
    def __post_init__(self):
        if self.authors is None:
            self.authors = []


class ElsevierClient:
    """Client for Elsevier APIs (ScienceDirect, Scopus)."""
    
    def __init__(self, api_key: str, proxy_auth=None):
        self.api_key = api_key
        self.proxy_auth = proxy_auth
        self.session = proxy_auth.session if proxy_auth else requests.Session()
        self.headers = {
            "X-ELS-APIKey": api_key,
            "Accept": "application/json",
        }
    
    def _fetch(self, url: str, headers: dict, params: dict = None) -> "requests.Response":
        if self.proxy_auth:
            kwargs = {"headers": headers, "timeout": 30}
            if params:
                kwargs["params"] = params
            return self.proxy_auth.fetch(url, **kwargs)
        kwargs = {"headers": headers, "timeout": 30}
        if params:
            kwargs["params"] = params
        return self.session.get(url, **kwargs)
    
    def get_article_by_doi(self, doi: str) -> Optional[ElsevierArticle]:
        """Fetch article metadata and full text by DOI.
        
        Args:
            doi: Digital Object Identifier
            
        Returns:
            ElsevierArticle or None
        """
        url = f"{ELSEVIER_API_BASE}/content/article/doi/{doi}"
        
        try:
            # First get metadata via JSON
            resp = self._fetch(url, self.headers)
            
            if resp.status_code == 404:
                logger.warning("Article not found: %s", doi)
                return None
            
            if resp.status_code == 403:
                logger.error("Access denied (check API key and subscription): %s", doi)
                return None
            
            resp.raise_for_status()
            data = resp.json()
            article = self._parse_metadata(data)
            
            # Now try to get full text via XML
            xml_headers = {**self.headers, "Accept": "text/xml"}
            xml_resp = self._fetch(url, xml_headers)
            
            if xml_resp.status_code == 200:
                full_text = self._extract_full_text_xml(xml_resp.text)
                if full_text:
                    article.full_text = full_text
                    logger.info("Extracted %d chars of full text from XML", len(full_text))
            
            return article
            
        except requests.RequestException as e:
            logger.error("Failed to fetch article %s: %s", doi, e)
            return None
    
    def get_full_text_by_pii(self, pii: str) -> Optional[str]:
        """Fetch full text by PII (Pubmed ID for Elsevier).
        
        Args:
            pii: Publisher Item Identifier
            
        Returns:
            Full text string or None
        """
        url = f"{ELSEVIER_API_BASE}/content/article/pii/{pii}"
        headers = {**self.headers, "Accept": "text/xml"}
        
        try:
            resp = self._fetch(url, headers)
            
            if resp.status_code == 404:
                logger.warning("Full text not found for PII: %s", pii)
                return None
            
            if resp.status_code == 403:
                logger.error("Access denied for PII: %s", pii)
                return None
            
            resp.raise_for_status()
            
            # Parse full text from XML
            return self._extract_full_text_xml(resp.text)
            
        except requests.RequestException as e:
            logger.error("Failed to fetch full text for PII %s: %s", pii, e)
            return None
    
    def search(self, query: str, limit: int = 10) -> list:
        """Search ScienceDirect for articles.
        
        Args:
            query: Search query
            limit: Maximum results
            
        Returns:
            List of article DOIs
        """
        url = f"{ELSEVIER_API_BASE}/content/search/sciencedirect"
        params = {
            "query": query,
            "count": limit,
        }
        
        try:
            resp = self._fetch(url, self.headers, params)
            resp.raise_for_status()
            data = resp.json()
            
            results = []
            entries = data.get("search-results", {}).get("entry", [])
            for entry in entries:
                doi = entry.get("prism:doi", "") or entry.get("dc:identifier", "").replace("DOI:", "")
                if doi:
                    results.append(doi)
            
            return results
            
        except requests.RequestException as e:
            logger.error("Search failed: %s", e)
            return []
    
    def _parse_metadata(self, data: dict) -> ElsevierArticle:
        article = ElsevierArticle()
        
        # Navigate the full-text-links structure
        ftl = data.get("full-text-retrieval-response", {})
        
        article.doi = ftl.get("coredata", {}).get("prism:doi", "")
        article.title = ftl.get("coredata", {}).get("dc:title", "")
        article.journal = ftl.get("coredata", {}).get("prism:publicationName", "")
        article.pii = ftl.get("coredata", {}).get("pii", "")
        
        # Year
        date_str = ftl.get("coredata", {}).get("prism:coverDate", "")
        if date_str and len(date_str) >= 4:
            article.year = int(date_str[:4])
        
        # Authors
        authors_data = ftl.get("coredata", {}).get("dc:creator", [])
        if isinstance(authors_data, list):
            for author in authors_data:
                name = author.get("$", "")
                if name:
                    article.authors.append(name)
        
        # Abstract
        article.abstract = ftl.get("coredata", {}).get("dc:description", "")
        
        # Full text will be fetched separately via XML endpoint
        # originalText in JSON is just indexing data, not real content
        
        return article
    
    def _extract_full_text_xml(self, xml_text: str) -> str:
        """Extract full text from ScienceDirect XML response."""
        import re
        
        # Extract text from XML body
        text_parts = []
        
        # Find all text content in body
        body_match = re.search(r'<body[^>]*>(.*?)</body>', xml_text, re.DOTALL | re.IGNORECASE)
        if body_match:
            body_text = body_match.group(1)
            # Remove XML tags
            clean_text = re.sub(r'<[^>]+>', ' ', body_text)
            # Clean up whitespace
            clean_text = re.sub(r'\s+', ' ', clean_text).strip()
            if clean_text:
                text_parts.append(clean_text)
        
        # Also check abstract
        abstract_match = re.search(r'<dc:description[^>]*>(.*?)</dc:description>', xml_text, re.DOTALL | re.IGNORECASE)
        if abstract_match:
            abstract = re.sub(r'<[^>]+>', ' ', abstract_match.group(1))
            abstract = re.sub(r'\s+', ' ', abstract).strip()
            if abstract:
                text_parts.insert(0, f"ABSTRACT: {abstract}")
        
        return "\n\n".join(text_parts) if text_parts else ""


def fetch_elsevier_article(doi: str, api_key: str) -> Optional[ElsevierArticle]:
    """Fetch article from Elsevier API.
    
    Args:
        doi: Article DOI
        api_key: Elsevier API key
        
    Returns:
        ElsevierArticle or None
    """
    client = ElsevierClient(api_key)
    return client.get_article_by_doi(doi)
