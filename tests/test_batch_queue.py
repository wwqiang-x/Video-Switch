"""Tests for the batch conversion queue."""

from pathlib import Path

from video_switch.models.media_info import MediaInfo
from video_switch.models.media_task import MediaTask, TaskStatus
from video_switch.services.conversion_runner import ConversionResult, ConversionRunner
from video_switch.services.history_store import ConversionHistoryStore
from video_switch.ui.batch_dialogs import BatchCandidate, BatchSelectionDialog
from video_switch.ui.main_window import MainWindow

FFMPEG_STUB = Path("ffmpeg.exe")


def _window_with_tasks(
    qtbot,
    tmp_path,
    isolated_settings,
    count: int = 3,
    ready: int = 3,
):
    """Build a window whose queue holds ``count`` videos, ``ready`` of them readable."""
    window = MainWindow(settings=isolated_settings)
    qtbot.addWidget(window)
    window.history_store = ConversionHistoryStore(tmp_path / "history.json")
    sources = []
    for index in range(count):
        video = tmp_path / f"clip_{index}.mp4"
        video.write_bytes(f"video {index}".encode())
        sources.append(video)
    window._import_paths([str(path) for path in sources], show_feedback=False)
    tasks = window._tasks_in_list_order()
    for index, task in enumerate(tasks):
        if index < ready:
            task.media_info = MediaInfo(duration_seconds=30.0, width=1280, height=720)
            task.status = TaskStatus.METADATA_READY
    window._available_ffmpeg_path = lambda: FFMPEG_STUB
    return window, tasks


def _record_starts(window) -> list[str]:
    """Replace the real conversion start with a recorder."""
    started: list[str] = []

    def fake_start() -> bool:
        started.append(window._current_task_key())
        return True

    window._start_conversion = fake_start
    return started


def _auto_confirm_dialogs(window) -> None:
    """Skip the interactive batch dialogs: select every readable task and confirm."""

    def select(queued) -> set[str] | None:
        keys = {task.key for task in queued if task.media_info is not None}
        return keys or None

    window._ask_batch_selection = select
    window._ask_batch_confirmation = lambda _selected: True


def _result(task: MediaTask, *, success: bool = True, cancelled: bool = False):
    return ConversionResult(
        task_key=task.key,
        source_key=task.content_signature,
        source_path=task.path,
        output_format="MP4",
        output_path=task.path.parent / "converted" / f"{task.path.stem}_converted.mp4",
        success=success,
        cancelled=cancelled,
        error=None if success else "转换失败",
        log="",
        elapsed_seconds=1.0,
        can_resume=False,
        progress_percent=100.0 if success else 0.0,
    )


def test_batch_conversion_runs_every_task_in_order(
    qtbot,
    tmp_path,
    isolated_settings,
) -> None:
    window, tasks = _window_with_tasks(qtbot, tmp_path, isolated_settings)
    started = _record_starts(window)
    _auto_confirm_dialogs(window)

    window._start_batch_conversion()

    assert window.batch_running is True
    assert window.batch_total == 3
    assert started == [tasks[0].key]
    assert window.batch_progress_label.text() == "批量 1/3"
    assert window.cancel_button.text() == "取消全部"
    # Both action buttons stay in the row; only their enabled state changes.
    assert window.start_button.isVisibleTo(window) is True
    assert window.start_button.isEnabled() is False
    assert window.batch_button.isVisibleTo(window) is True
    assert window.batch_button.isEnabled() is False

    window._on_conversion_finished(_result(tasks[0]))
    qtbot.waitUntil(lambda: len(started) == 2)
    assert started[1] == tasks[1].key
    assert window.batch_counts["success"] == 1

    window._on_conversion_finished(_result(tasks[1], success=False))
    qtbot.waitUntil(lambda: len(started) == 3)
    assert started[2] == tasks[2].key
    assert window.batch_counts["failed"] == 1

    window._on_conversion_finished(_result(tasks[2]))
    qtbot.waitUntil(lambda: window.batch_running is False)

    assert window.batch_counts == {"success": 2, "failed": 1, "cancelled": 0, "skipped": 0}
    assert window.batch_progress_label.isVisibleTo(window) is False
    assert window.cancel_button.text() == "取消转换"
    assert window.start_button.isVisibleTo(window) is True
    assert window.start_button.isEnabled() is True
    assert window.batch_button.isVisibleTo(window) is True
    footer = window.footer_status_label.text()
    assert "批量转换完成" in footer
    assert "成功 2" in footer
    assert "失败 1" in footer


def test_batch_conversion_skips_unreadable_tasks(
    qtbot,
    tmp_path,
    isolated_settings,
) -> None:
    window, tasks = _window_with_tasks(qtbot, tmp_path, isolated_settings, count=3, ready=1)
    started = _record_starts(window)
    _auto_confirm_dialogs(window)

    window._start_batch_conversion()

    assert window.batch_total == 1
    assert window.batch_counts["skipped"] == 2
    assert started == [tasks[0].key]

    window._on_conversion_finished(_result(tasks[0]))
    qtbot.waitUntil(lambda: window.batch_running is False)

    assert "跳过 2" in window.footer_status_label.text()


def test_batch_conversion_needs_a_ready_task(
    qtbot,
    tmp_path,
    isolated_settings,
) -> None:
    window, _tasks = _window_with_tasks(qtbot, tmp_path, isolated_settings, count=1, ready=0)

    window._start_batch_conversion()

    assert window.batch_running is False
    assert "没有可转换的视频" in window.footer_status_label.text()


def test_cancel_stops_the_remaining_batch_tasks(
    qtbot,
    tmp_path,
    isolated_settings,
    monkeypatch,
) -> None:
    window, tasks = _window_with_tasks(qtbot, tmp_path, isolated_settings)
    started = _record_starts(window)
    _auto_confirm_dialogs(window)
    window._start_batch_conversion()

    monkeypatch.setattr(ConversionRunner, "is_running", property(lambda self: True))
    try:
        window._cancel_conversion()
    finally:
        # is_running must go back to False before widget teardown closes the window.
        monkeypatch.undo()

    assert window.batch_pending == []
    assert window.batch_cancelled is True

    window._on_conversion_finished(_result(tasks[0], success=False, cancelled=True))
    qtbot.waitUntil(lambda: window.batch_running is False)

    assert started == [tasks[0].key]
    assert window.batch_counts["cancelled"] == 1
    assert "已取消批量转换" in window.footer_status_label.text()


def test_batch_conversion_only_runs_ticked_videos(
    qtbot,
    tmp_path,
    isolated_settings,
) -> None:
    window, tasks = _window_with_tasks(qtbot, tmp_path, isolated_settings)
    tasks[0].status = TaskStatus.COMPLETED
    started = _record_starts(window)
    window._ask_batch_selection = lambda _queued: {tasks[1].key}
    window._ask_batch_confirmation = lambda _selected: True

    window._start_batch_conversion()

    assert window.batch_total == 1
    assert started == [tasks[1].key]


def test_batch_selection_dialog_prechecks_pending_videos(qtbot) -> None:
    candidates = [
        BatchCandidate("a", "done.mp4", "MP4 · 已完成", checked=False),
        BatchCandidate("b", "new.mp4", "MP4 · 已读取", checked=True),
        BatchCandidate(
            "c",
            "broken.mp4",
            "MP4 · 待读取",
            checked=True,
            reason="媒体信息尚未读取完成，本次不参与批量转换",
        ),
    ]
    dialog = BatchSelectionDialog(candidates)
    qtbot.addWidget(dialog)

    assert dialog.selected_keys == ["b"]
    assert dialog.selection_label.text() == "已选择 1/2"

    dialog.select_all_box.setChecked(True)
    assert dialog.selected_keys == ["a", "b"]

    dialog.select_all_box.setChecked(False)
    assert dialog.selected_keys == []
    assert dialog.next_button.isEnabled() is False


def test_batch_candidates_mark_unreadable_videos(
    qtbot,
    tmp_path,
    isolated_settings,
    monkeypatch,
) -> None:
    window, tasks = _window_with_tasks(qtbot, tmp_path, isolated_settings, count=3, ready=2)
    tasks[0].status = TaskStatus.COMPLETED
    captured: list[BatchCandidate] = []

    class FakeDialog:
        def __init__(self, candidates, parent=None) -> None:
            del parent
            captured.extend(candidates)

        def exec(self) -> int:
            return 0

        selected_keys: list[str] = []

    monkeypatch.setattr("video_switch.ui.main_window.BatchSelectionDialog", FakeDialog)

    window._start_batch_conversion()

    assert [candidate.checked for candidate in captured] == [False, True, True]
    assert captured[2].selectable is False
    assert "媒体信息" in captured[2].reason
    assert window.batch_running is False


def test_cancelling_the_selection_dialog_keeps_the_queue_untouched(
    qtbot,
    tmp_path,
    isolated_settings,
) -> None:
    window, _tasks = _window_with_tasks(qtbot, tmp_path, isolated_settings)
    started = _record_starts(window)
    window._ask_batch_selection = lambda _queued: None

    window._start_batch_conversion()

    assert started == []
    assert window.batch_running is False


def test_batch_watchdog_recovers_a_stalled_batch(
    qtbot,
    tmp_path,
    isolated_settings,
) -> None:
    """A batch whose runner stopped must not leave the buttons stuck forever."""
    window, tasks = _window_with_tasks(qtbot, tmp_path, isolated_settings)
    started = _record_starts(window)
    _auto_confirm_dialogs(window)
    window._start_batch_conversion()
    assert window.batch_total == 3

    # Simulate a batch that lost its runner without reporting a result.
    window.batch_pending = [task.key for task in tasks[1:]]
    window.batch_running = True
    window._batch_watchdog.start()

    qtbot.waitUntil(lambda: window.batch_running is False, timeout=5000)

    assert window.start_button.isVisibleTo(window) is True
    assert window.batch_button.isVisibleTo(window) is True
    assert started == [tasks[0].key, tasks[1].key, tasks[2].key]


def test_removing_a_pending_task_drops_it_from_the_batch(
    qtbot,
    tmp_path,
    isolated_settings,
) -> None:
    window, tasks = _window_with_tasks(qtbot, tmp_path, isolated_settings)
    _record_starts(window)
    _auto_confirm_dialogs(window)
    window._start_batch_conversion()
    window.task_list.setCurrentItem(window.task_items[tasks[2].key])

    window._remove_selected_task()

    assert tasks[2].key not in window.batch_pending
    assert window.batch_total == 2
    assert window.batch_counts["skipped"] == 1
