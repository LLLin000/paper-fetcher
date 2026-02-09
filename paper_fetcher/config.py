"""Configuration management for paper-fetcher."""

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_BASE_DIR = Path.home() / ".paper-fetcher"


@dataclass
class Config:
    """Paper fetcher configuration."""

    proxy_base: str = ""
    email: str = ""  # Set via 'paper-fetcher config-cmd --email your@email.com'
    output_dir: str = ""
    cache_dir: str = ""
    cookie_path: str = ""
    chrome_profile_dir: str = ""
    request_delay_min: float = 2.0
    request_delay_max: float = 5.0

    def __post_init__(self):
        base = DEFAULT_BASE_DIR
        if not self.output_dir:
            self.output_dir = str(base / "papers")
        if not self.cache_dir:
            self.cache_dir = str(base / "cache")
        if not self.cookie_path:
            self.cookie_path = str(base / "cookies.json")
        if not self.chrome_profile_dir:
            self.chrome_profile_dir = str(base / "chrome-profile")

    def ensure_dirs(self):
        """Create all necessary directories."""
        for d in [self.output_dir, self.cache_dir, self.chrome_profile_dir]:
            Path(d).mkdir(parents=True, exist_ok=True)
        Path(self.cookie_path).parent.mkdir(parents=True, exist_ok=True)

    def save(self, path: Path | None = None):
        """Save config to JSON file."""
        path = path or (DEFAULT_BASE_DIR / "config.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path | None = None) -> "Config":
        """Load config from JSON file, falling back to defaults."""
        path = path or (DEFAULT_BASE_DIR / "config.json")
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning("Failed to load config from %s: %s. Using defaults.", path, e)
        return cls()
