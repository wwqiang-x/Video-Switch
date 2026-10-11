"""Shared pytest fixtures."""

import pytest
from PySide6.QtCore import QSettings


@pytest.fixture
def isolated_settings(tmp_path):
    """Provide a temporary QSettings file for UI tests."""
    return QSettings(
        str(tmp_path / "settings.ini"),
        QSettings.Format.IniFormat,
    )
