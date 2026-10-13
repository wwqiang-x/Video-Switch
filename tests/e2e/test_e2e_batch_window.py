"""Batch conversion driven through the real window, probes and FFmpeg."""

from pathlib import Path

import pytest

from video_switch.services.history_store import ConversionHistoryStore
from video_switch.services.toolchain import ToolchainStatus, ToolInfo
from video_switch.ui.main_window import MainWindow

pytestmark = pytest.mark.slow


def test_window_batch_converts_readable_files_and_skips_broken_ones(
    qtbot,
    tmp_path: Path,
    isolated_settings,
    ffmpeg_path: Path,
    ffprobe_path: Path,
    make_clip,
) -> None:
    window = MainWindow(settings=isolated_settings)
    qtbot.addWidget(window)
    window.history_store = ConversionHistoryStore(tmp_path / "history.json")
    window.history_records = []
    output_dir = tmp_path / "out"
    window.output_directory = output_dir
    window._update_output_preview()

    first = make_clip(tmp_path / "first.mp4", 1.5)
    second = make_clip(tmp_path / "second.mp4", 1.5, size="240x180")
    broken = tmp_path / "broken.mp4"
    broken.write_bytes(b"definitely not a video")
    window._import_paths([str(first), str(second), str(broken)], show_feedback=False)

    window._on_toolchain_detected(
        ToolchainStatus(
            ffmpeg=ToolInfo(name="ffmpeg", executable=ffmpeg_path, version="6.0"),
            ffprobe=ToolInfo(name="ffprobe", executable=ffprobe_path, version="6.0"),
        )
    )
    tasks = window._tasks_in_list_order()
    qtbot.waitUntil(
        lambda: all(task.media_info is not None or task.probe_error for task in tasks),
        timeout=60_000,
    )

    messages: list[str] = []
    original_footer = window._show_footer_message

    def record(message: str, details: str = "", state=None, timeout: int = 0) -> None:
        messages.append(message)
        original_footer(message, details, state, timeout)

    window._show_footer_message = record
    window._ask_batch_selection = lambda queued: {
        task.key for task in queued if task.media_info is not None
    }
    window._ask_batch_confirmation = lambda _selected: True

    window._start_batch_conversion()
    qtbot.waitUntil(
        lambda: not window.batch_running and not window.conversion_runner.is_running,
        timeout=180_000,
    )

    assert window.batch_counts["success"] == 2
    assert window.batch_counts["skipped"] == 1
    summary = next(message for message in messages if "批量转换完成" in message)
    assert "成功 2" in summary
    assert "跳过 1" in summary

    produced = sorted(path.name for path in output_dir.glob("*.mp4"))
    assert len(produced) == 2
    assert all(path.stat().st_size > 0 for path in output_dir.glob("*.mp4"))

    # 每个任务只显示自己的历史记录
    for task in tasks:
        window.task_list.setCurrentItem(window.task_items[task.key])
        records = window._history_records_for_source(task.content_signature)
        assert window.history_list.count() == len(records)
