"""Progress display utilities using rich library."""

from typing import Optional

try:
    from rich.progress import (
        Progress,
        SpinnerColumn,
        TextColumn,
        BarColumn,
        TaskProgressColumn,
        TimeRemainingColumn,
    )
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False


class DownloadProgress:
    """Progress tracker for downloads."""

    def __init__(self, total: int, description: str = "Downloading"):
        self.total = total
        self.current = 0
        self._progress: Optional[Progress] = None
        self._task_id = None

        if RICH_AVAILABLE:
            self._progress = Progress(
                SpinnerColumn(),
                TextColumn("[bold blue]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                TimeRemainingColumn(),
            )
            self._task_id = self._progress.add_task(
                description, total=total
            )
            self._progress.start()
        else:
            print(f"{description}: 0/{total}")

    def update(self, advance: int = 1):
        """Update progress."""
        self.current += advance
        if self._progress and self._task_id is not None:
            self._progress.update(self._task_id, advance=advance)
        else:
            print(f"Progress: {self.current}/{self.total}")

    def complete(self):
        """Mark progress as complete."""
        if self._progress:
            self._progress.stop()
        else:
            print(f"Complete: {self.current}/{self.total}")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.complete()
