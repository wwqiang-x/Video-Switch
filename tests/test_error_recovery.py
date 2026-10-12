"""Tests for step 9: friendly errors, retry and resume after a restart."""

import sys
from pathlib import Path

from video_switch.models.media_info import MediaInfo
from video_switch.models.media_task import TaskStatus
from video_switch.services import crash_handler
from video_switch.services.error_messages import (
    FALLBACK_CONVERSION,
    SOURCE_MISSING,
    describe_conversion_error,
    describe_probe_error,
    last_meaningful_line,
)
from video_switch.services.history_store import ConversionHistoryStore
from video_switch.services.media_probe import ProbeResult
from video_switch.ui.main_window import MainWindow

FFMPEG_STUB = Path("ffmpeg.exe")


def _window_with_tasks(qtbot, tmp_path, isolated_settings, count: int = 2, ready: int = 2):
    window = MainWindow(settings=isolated_settings)
    qtbot.addWidget(window)
    window.history_store = ConversionHistoryStore(tmp_path / "history.json")
    window.history_records = []
    sources = []
    for index in range(count):
        video = tmp_path / f"clip_{index}.mp4"
        video.write_bytes(f"video {index}".encode())
        sources.append(video)
    window._import_paths([str(path) for path in sources], show_feedback=False)
    tasks = window._tasks_in_list_order()
    for index, task in enumerate(tasks):
        if index < ready:
            task.media_info = MediaInfo(duration_seconds=120.0, width=1280, height=720)
            task.status = TaskStatus.METADATA_READY
    window._available_ffmpeg_path = lambda: FFMPEG_STUB
    return window, tasks


def test_describe_conversion_error_covers_common_causes() -> None:
    assert "磁盘空间不足" in describe_conversion_error(
        "av_interleaved_write_frame(): No space left on device"
    )
    assert "无法写入输出目录" in describe_conversion_error(
        "Error opening output file D:\\out\\x.mp4: Permission denied"
    )
    assert describe_conversion_error("D:\\clip.mp4: No such file or directory") == SOURCE_MISSING
    assert "无法解析" in describe_conversion_error(
        "D:\\clip.mp4: Invalid data found when processing input"
    )
    assert "编码器" in describe_conversion_error("Unknown encoder 'libfoo'")
    assert "参数组合" in describe_conversion_error("Invalid argument")
    assert "占用" in describe_conversion_error(
        "The process cannot access the file because it is being used by another process"
    )


def test_describe_conversion_error_falls_back_to_last_line() -> None:
    message = describe_conversion_error("line one\nError while filtering: something odd")

    assert message.startswith(FALLBACK_CONVERSION)
    assert "something odd" in message
    assert describe_conversion_error("") == FALLBACK_CONVERSION


def test_last_meaningful_line_skips_blanks() -> None:
    assert last_meaningful_line("\n\nhello\n\n") == "hello"
    assert last_meaningful_line("") == ""


def test_describe_probe_error_is_user_friendly() -> None:
    assert "损坏" in describe_probe_error("clip.mp4: Invalid data found when processing input")
    assert "移动" in describe_probe_error("clip.mp4: No such file or directory")
    assert "权限" in describe_probe_error("Permission denied")
    assert "超时" in describe_probe_error("ffprobe timed out")
    assert describe_probe_error("") == describe_probe_error("完全未知的错误")


def test_crash_handler_writes_the_log(monkeypatch, tmp_path) -> None:
    log_path = tmp_path / "logs" / "video-switch.log"
    monkeypatch.setattr(crash_handler, "default_log_path", lambda: log_path)
    notified: list[str] = []
    original_hook = sys.excepthook
    monkeypatch.setattr(sys, "excepthook", original_hook)

    crash_handler.install_exception_hook(notified.append)
    try:
        raise ValueError("boom")
    except ValueError:
        sys.excepthook(*sys.exc_info())

    text = log_path.read_text(encoding="utf-8")
    assert "ValueError" in text
    assert "boom" in text
    assert notified == [str(log_path)]


def test_crash_handler_rotates_a_oversized_log(monkeypatch, tmp_path) -> None:
    log_path = tmp_path / "video-switch.log"
    log_path.write_text("x" * (crash_handler.MAX_LOG_BYTES + 100), encoding="utf-8")
    monkeypatch.setattr(crash_handler, "default_log_path", lambda: log_path)

    crash_handler.write_log_entry("new entry", log_path)

    text = log_path.read_text(encoding="utf-8")
    assert text.endswith("new entry")
    assert len(text) < crash_handler.MAX_LOG_BYTES


def test_missing_source_is_reported_before_conversion(
    qtbot,
    tmp_path,
    isolated_settings,
) -> None:
    window, tasks = _window_with_tasks(qtbot, tmp_path, isolated_settings, count=1)
    task = tasks[0]
    task.path.unlink()

    started = window._start_conversion()

    assert started is False
    assert task.status == TaskStatus.FAILED
    assert task.conversion_error == SOURCE_MISSING
    assert SOURCE_MISSING in window.footer_status_label.text()


def test_resume_state_survives_a_restart(
    qtbot,
    tmp_path,
    isolated_settings,
) -> None:
    first_window, tasks = _window_with_tasks(qtbot, tmp_path, isolated_settings, count=1)
    task = tasks[0]
    part_dir = tmp_path / "converted" / ".clip_0.abc.parts"
    part_dir.mkdir(parents=True)
    for index in range(2):
        (part_dir / f"part_{index:05d}.mp4").write_bytes(b"segment")
    task.conversion_part_dir = part_dir
    task.conversion_settings_key = "abc"
    task.conversion_parts_completed = 2
    task.conversion_resumable = True
    first_window._remember_resume_dir(task)
    isolated_settings.sync()

    second_window = MainWindow(settings=isolated_settings)
    qtbot.addWidget(second_window)
    second_window.history_store = ConversionHistoryStore(tmp_path / "history.json")
    second_window._restore_saved_tasks()

    restored = next(iter(second_window.tasks.values()))
    # Metadata is not read yet, so the task must stay in the queue's pending state.
    assert restored.status == TaskStatus.WAITING_FOR_METADATA
    assert restored.conversion_resumable is True
    assert restored.conversion_part_dir == part_dir
    assert restored.conversion_parts_completed == 2

    second_window._on_task_probe_finished(
        ProbeResult(
            task_key=restored.key,
            path=restored.path,
            info=MediaInfo(duration_seconds=120.0, width=1280, height=720),
        )
    )

    assert restored.status == TaskStatus.CANCELLED
    assert "上次转换被中断" in (restored.conversion_error or "")
    assert restored.conversion_progress == 50.0
    assert "继续转换" in second_window.footer_status_label.text()


def test_clearing_a_cancelled_state_forgets_the_resume_entry(
    qtbot,
    tmp_path,
    isolated_settings,
) -> None:
    window, tasks = _window_with_tasks(qtbot, tmp_path, isolated_settings, count=1)
    task = tasks[0]
    part_dir = tmp_path / "converted" / ".clip_0.abc.parts"
    part_dir.mkdir(parents=True)
    (part_dir / "part_00000.mp4").write_bytes(b"segment")
    task.conversion_part_dir = part_dir
    task.conversion_resumable = True
    task.conversion_parts_completed = 1
    task.status = TaskStatus.CANCELLED
    window._remember_resume_dir(task)
    window._confirm_discard_progress = lambda _task: True

    window._clear_conversion_state()
    isolated_settings.sync()

    assert window._resume_map() == {}
    assert part_dir.exists() is False
    second_window = MainWindow(settings=isolated_settings)
    qtbot.addWidget(second_window)
    second_window._restore_saved_tasks()
    restored = next(iter(second_window.tasks.values()))
    assert restored.conversion_resumable is False
    assert restored.status != TaskStatus.CANCELLED


def test_retry_button_only_runs_failed_tasks(
    qtbot,
    tmp_path,
    isolated_settings,
) -> None:
    window, tasks = _window_with_tasks(qtbot, tmp_path, isolated_settings, count=3)
    tasks[1].status = TaskStatus.FAILED
    tasks[1].conversion_error = "转换失败"
    tasks[2].status = TaskStatus.COMPLETED
    started: list[str] = []

    def fake_start() -> bool:
        started.append(window._current_task_key())
        return True

    window._start_conversion = fake_start
    window._update_conversion_controls()

    assert window.retry_button.isVisibleTo(window) is True

    window._ask_batch_confirmation = lambda _selected: True
    window._retry_failed_tasks()

    assert window.batch_total == 1
    assert started == [tasks[1].key]


def test_retry_button_hides_without_failures(
    qtbot,
    tmp_path,
    isolated_settings,
) -> None:
    window, _tasks = _window_with_tasks(qtbot, tmp_path, isolated_settings)

    window._update_conversion_controls()

    assert window.retry_button.isVisibleTo(window) is False
