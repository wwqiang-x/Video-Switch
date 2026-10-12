"""Record unexpected exceptions so a crash leaves behind a readable log."""

from __future__ import annotations

import sys
import tempfile
import traceback
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from types import TracebackType

from PySide6.QtCore import QStandardPaths

LOG_FILE_NAME = "video-switch.log"
MAX_LOG_BYTES = 512 * 1024


def default_log_path() -> Path:
    """Return the per-user log file used for unexpected errors."""
    data_root = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
    base = Path(data_root) if data_root else Path(tempfile.gettempdir())
    return base / "logs" / LOG_FILE_NAME


def format_exception(
    exc_type: type[BaseException] | None,
    exc_value: BaseException | None,
    exc_tb: TracebackType | None,
) -> str:
    """Render one exception with a timestamp header."""
    stamp = datetime.now().astimezone().isoformat(timespec="seconds")
    trace = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    return f"\n===== {stamp} =====\n{trace}"


def write_log_entry(text: str, path: Path | None = None) -> Path:
    """Append one entry, truncating the file once it grows past the limit."""
    target = path or default_log_path()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.is_file() and target.stat().st_size > MAX_LOG_BYTES:
            previous = target.read_text(encoding="utf-8", errors="replace")
            target.write_text(previous[-MAX_LOG_BYTES // 2 :], encoding="utf-8")
        with target.open("a", encoding="utf-8") as handle:
            handle.write(text)
    except OSError:
        pass
    return target


def install_exception_hook(notify: Callable[[str], None] | None = None) -> Path:
    """Log unhandled exceptions and report the log path to the user once."""
    log_path = default_log_path()
    reported = False

    def hook(
        exc_type: type[BaseException],
        exc_value: BaseException,
        exc_tb: TracebackType | None,
    ) -> None:
        nonlocal reported
        traceback.print_exception(exc_type, exc_value, exc_tb)
        write_log_entry(format_exception(exc_type, exc_value, exc_tb), log_path)
        if notify is not None and not reported:
            reported = True
            try:
                notify(str(log_path))
            except Exception:  # noqa: BLE001 - the hook must never raise again
                pass

    sys.excepthook = hook
    return log_path
