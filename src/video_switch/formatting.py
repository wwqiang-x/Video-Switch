"""Shared display formatting so every screen reports numbers the same way."""

from __future__ import annotations


def format_duration(seconds: float | None) -> str:
    """Format a duration as ``MM:SS``, switching to ``HH:MM:SS`` past an hour."""
    if seconds is None:
        return "--"
    total = max(0, int(round(seconds)))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def format_speed(text: str | None) -> str:
    """Normalise FFmpeg's ``1.24x`` speed into the app's ``1.24×`` notation."""
    if not text:
        return ""
    value = text.strip()
    if value.endswith(("x", "X")):
        value = f"{value[:-1]}×"
    return value
