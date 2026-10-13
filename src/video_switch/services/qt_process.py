"""Small QProcess helpers shared by the background services."""

from __future__ import annotations

import warnings

from PySide6.QtCore import QProcess


def detach_process(process: QProcess | None) -> None:
    """Drop the signals of a finished or cancelled QProcess.

    Qt reports a failed ``disconnect()`` as a ``RuntimeWarning`` rather than an
    exception, so the warning is silenced explicitly: there is nothing to detach
    when the process was never started, which is exactly the case in tests.
    """
    if process is None:
        return
    for signal in (process.finished, process.errorOccurred):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            try:
                signal.disconnect()
            except (RuntimeError, TypeError):  # pragma: no cover - defensive
                pass
