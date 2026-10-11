"""Locate and validate the local FFmpeg command-line tools."""

from __future__ import annotations

import os
import re
import shutil
import sys
from collections import deque
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, QTimer, Signal

TOOL_NAMES = ("ffmpeg", "ffprobe")
TOOL_SUBDIRS = (
    Path("ffmpeg") / "bin",
    Path("tools") / "ffmpeg" / "bin",
    Path(".tools") / "ffmpeg" / "bin",
    Path("vendor") / "ffmpeg" / "bin",
)
PROBE_TIMEOUT_MS = 4000


@dataclass(frozen=True)
class ToolInfo:
    """Validation result for one command-line tool."""

    name: str
    executable: Path | None = None
    version: str | None = None
    source: str | None = None
    error: str | None = None

    @property
    def ready(self) -> bool:
        return self.executable is not None and self.version is not None

    @property
    def display_version(self) -> str:
        if not self.version:
            return ""
        match = re.match(r"(\d+(?:\.\d+){1,2})", self.version)
        return match.group(1) if match else self.version


@dataclass(frozen=True)
class ToolchainStatus:
    """Combined validation result for ffmpeg and ffprobe."""

    ffmpeg: ToolInfo
    ffprobe: ToolInfo

    @property
    def ready(self) -> bool:
        return self.ffmpeg.ready and self.ffprobe.ready

    @property
    def summary(self) -> str:
        if self.ready:
            return f"FFmpeg {self.ffmpeg.display_version} · 环境就绪"
        missing = [tool for tool in (self.ffmpeg, self.ffprobe) if not tool.ready]
        if len(missing) == 2:
            return "未找到 FFmpeg 和 ffprobe，请打开设置"
        return f"{missing[0].name} 未就绪，请打开设置"


def executable_name(name: str) -> str:
    """Return the platform-specific executable filename."""
    return f"{name}.exe" if os.name == "nt" else name


def application_roots() -> tuple[Path, ...]:
    """Return possible roots for bundled and development tool binaries."""
    roots: list[Path] = []
    if getattr(sys, "frozen", False):
        roots.append(Path(sys.executable).resolve().parent)
        bundle_root = getattr(sys, "_MEIPASS", None)
        if bundle_root:
            roots.append(Path(bundle_root))
    else:
        roots.append(Path(__file__).resolve().parents[3])
    return tuple(dict.fromkeys(roots))


def resolve_tool(
    name: str,
    configured_path: str | None = None,
    roots: tuple[Path, ...] | None = None,
) -> tuple[Path | None, str | None]:
    """Resolve a tool from user settings, bundled locations, then PATH."""
    if configured_path:
        candidate = Path(configured_path).expanduser()
        if candidate.is_file():
            return candidate, "用户配置"

    search_roots = roots if roots is not None else application_roots()
    filename = executable_name(name)
    for root in search_roots:
        for subdir in TOOL_SUBDIRS:
            candidate = root / subdir / filename
            if candidate.is_file():
                return candidate, "应用内置"

    path_match = shutil.which(name)
    if path_match:
        return Path(path_match), "系统 PATH"
    return None, None


def parse_tool_version(name: str, output: str) -> str | None:
    """Extract a compact version string from ``tool -version`` output."""
    match = re.search(rf"\b{re.escape(name)} version\s+([^\s]+)", output)
    return match.group(1) if match else None


class _ToolProbe(QObject):
    """Asynchronously run ``tool -version`` with a timeout."""

    completed = Signal(object)

    def __init__(
        self,
        name: str,
        executable: Path,
        source: str,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.name = name
        self.executable = executable
        self.source = source
        self._completed = False
        self.process = QProcess(self)
        self.process.finished.connect(self._on_finished)
        self.process.errorOccurred.connect(self._on_error)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._on_timeout)

    def start(self) -> None:
        self.process.start(str(self.executable), ["-version"])
        self.timer.start(PROBE_TIMEOUT_MS)

    def cancel(self) -> None:
        self._completed = True
        self.timer.stop()
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self.process.kill()

    def _on_finished(
        self,
        exit_code: int,
        exit_status: QProcess.ExitStatus,
    ) -> None:
        del exit_status
        output = bytes(self.process.readAllStandardOutput()).decode(errors="replace")
        if not output:
            output = bytes(self.process.readAllStandardError()).decode(errors="replace")

        if exit_code == 0:
            version = parse_tool_version(self.name, output)
            if version:
                self._complete(
                    ToolInfo(
                        name=self.name,
                        executable=self.executable,
                        version=version,
                        source=self.source,
                    )
                )
                return

        self._complete(
            ToolInfo(
                name=self.name,
                executable=self.executable,
                source=self.source,
                error="程序执行失败或版本信息无法解析",
            )
        )

    def _on_error(self, error: QProcess.ProcessError) -> None:
        if error == QProcess.ProcessError.FailedToStart:
            self._complete(
                ToolInfo(
                    name=self.name,
                    executable=self.executable,
                    source=self.source,
                    error="无法启动程序，请检查文件是否完整",
                )
            )

    def _on_timeout(self) -> None:
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self.process.kill()
        self._complete(
            ToolInfo(
                name=self.name,
                executable=self.executable,
                source=self.source,
                error="版本检测超时",
            )
        )

    def _complete(self, result: ToolInfo) -> None:
        if self._completed:
            return
        self._completed = True
        self.timer.stop()
        self.completed.emit(result)


class ToolchainDetector(QObject):
    """Detect and validate ffmpeg and ffprobe without blocking the UI."""

    started = Signal()
    finished = Signal(object)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._generation = 0
        self._queue: deque[tuple[str, Path, str]] = deque()
        self._results: dict[str, ToolInfo] = {}
        self._probe: _ToolProbe | None = None
        self._next_timer = QTimer(self)
        self._next_timer.setSingleShot(True)
        self._next_timer.timeout.connect(self._start_queued_probe)
        self._queued_generation = 0

    def detect(
        self,
        configured_ffmpeg: str | None = None,
        configured_ffprobe: str | None = None,
    ) -> None:
        """Start a new detection run, replacing any previous run."""
        self.cancel()
        self._generation += 1
        generation = self._generation
        self._queue.clear()
        self._results.clear()

        configured = {
            "ffmpeg": configured_ffmpeg,
            "ffprobe": configured_ffprobe,
        }
        for name in TOOL_NAMES:
            executable, source = resolve_tool(name, configured[name])
            if executable is None:
                self._results[name] = ToolInfo(
                    name=name,
                    error=f"未找到 {name}",
                )
            else:
                self._queue.append((name, executable, source or "自动检测"))

        self.started.emit()
        self._start_next(generation)

    def cancel(self) -> None:
        """Cancel the active probe and invalidate pending results."""
        self._generation += 1
        self._next_timer.stop()
        if self._probe is not None:
            self._probe.cancel()
            self._probe = None
        self._queue.clear()

    def _start_next(self, generation: int) -> None:
        if generation != self._generation:
            return
        if not self._queue:
            self.finished.emit(
                ToolchainStatus(
                    ffmpeg=self._results["ffmpeg"],
                    ffprobe=self._results["ffprobe"],
                )
            )
            return

        name, executable, source = self._queue.popleft()
        self._probe = _ToolProbe(name, executable, source, self)
        self._probe.completed.connect(
            lambda result, run=generation: self._on_probe_complete(result, run)
        )
        self._probe.start()

    def _on_probe_complete(self, result: ToolInfo, generation: int) -> None:
        if generation != self._generation:
            return
        self._results[result.name] = result
        self._probe = None
        self._queued_generation = generation
        self._next_timer.start(0)

    def _start_queued_probe(self) -> None:
        self._start_next(self._queued_generation)
