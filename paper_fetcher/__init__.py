"""Paper Fetcher - Automated academic paper full-text fetcher with HKU EZproxy support."""

from .config import Config
from .fetcher import PaperFetcher
from .models import Paper

__all__ = ["PaperFetcher", "Paper", "Config"]
__version__ = "0.1.0"
