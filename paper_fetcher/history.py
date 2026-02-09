"""Search history management for paper-fetcher."""

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)

DEFAULT_HISTORY_FILE = Path.home() / ".paper-fetcher" / "history.json"
MAX_HISTORY_ITEMS = 100


@dataclass
class SearchRecord:
    """A single search record."""
    query: str
    source: str
    timestamp: str
    result_count: int = 0


class SearchHistory:
    """Manages search history."""

    def __init__(self, history_file: Path | None = None):
        self.history_file = history_file or DEFAULT_HISTORY_FILE
        self.history_file.parent.mkdir(parents=True, exist_ok=True)
        self._records: List[SearchRecord] = []
        self._load()

    def _load(self):
        """Load history from file."""
        if self.history_file.exists():
            try:
                data = json.loads(self.history_file.read_text(encoding="utf-8"))
                self._records = [
                    SearchRecord(**item) for item in data.get("records", [])
                ]
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning("Failed to load history: %s", e)
                self._records = []

    def save(self):
        """Save history to file."""
        data = {
            "records": [asdict(r) for r in self._records[-MAX_HISTORY_ITEMS:]]
        }
        self.history_file.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

    def add(self, query: str, source: str, result_count: int = 0):
        """Add a search record."""
        record = SearchRecord(
            query=query,
            source=source,
            timestamp=datetime.now().isoformat(),
            result_count=result_count
        )
        self._records.append(record)
        self.save()

    def get_recent(self, limit: int = 10) -> List[SearchRecord]:
        """Get recent search records."""
        return self._records[-limit:][::-1]

    def get_all(self) -> List[SearchRecord]:
        """Get all search records."""
        return self._records[::-1]

    def clear(self):
        """Clear all history."""
        self._records = []
        self.save()

    def search(self, keyword: str) -> List[SearchRecord]:
        """Search in history."""
        return [
            r for r in self._records
            if keyword.lower() in r.query.lower()
        ][::-1]
