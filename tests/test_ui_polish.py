"""Tests for step 10: queue status colours, footer progress, shortcuts, geometry."""

from pathlib import Path

from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QLineEdit, QStyleOptionViewItem

from video_switch.models.media_info import MediaInfo
from video_switch.models.media_task import TaskStatus
from video_switch.services.conversion_runner import ConversionProgress
from video_switch.services.history_store import ConversionHistoryStore
from video_switch.ui.main_window import MainWindow
from video_switch.ui.task_item_delegate import (
    ACCENT_ROLE,
    META_ROLE,
    NAME_ROLE,
    STATUS_COLOR_ROLE,
    STATUS_ROLE,
    TaskItemDelegate,
    status_color,
)
from video_switch.ui.theme import get_palette


def _window_with_tasks(qtbot, tmp_path, isolated_settings, count: int = 2):
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
    for task in tasks:
        task.media_info = MediaInfo(duration_seconds=60.0, width=1280, height=720)
        task.status = TaskStatus.METADATA_READY
    for task in tasks:
        window._update_task_item(task)
    window._available_ffmpeg_path = lambda: Path("ffmpeg.exe")
    return window, tasks


def _auto_dialogs(window, keys) -> None:
    window._ask_batch_selection = lambda _queued: set(keys)
    window._ask_batch_confirmation = lambda _selected: True


def test_every_state_gets_its_own_colour() -> None:
    palette = get_palette("light")

    assert status_color(TaskStatus.WAITING_FOR_METADATA, palette) == palette.muted
    assert status_color(TaskStatus.PROBING_METADATA, palette) == palette.muted
    assert status_color(TaskStatus.CONVERTING, palette) == palette.primary
    assert status_color(TaskStatus.COMPLETED, palette) == palette.success
    assert status_color(TaskStatus.FAILED, palette) == palette.danger
    assert status_color(TaskStatus.CANCELLED, palette) == palette.warning
    assert status_color(TaskStatus.METADATA_READY, palette) == palette.text
    assert len({status_color(status, palette) for status in TaskStatus}) >= 5


def test_queue_rows_carry_status_metadata(qtbot, tmp_path, isolated_settings) -> None:
    window, tasks = _window_with_tasks(qtbot, tmp_path, isolated_settings)
    palette = get_palette(window.theme_name)
    tasks[1].status = TaskStatus.FAILED
    tasks[1].conversion_error = "转换失败"
    window._update_task_item(tasks[1])

    ready_item = window.task_items[tasks[0].key]
    failed_item = window.task_items[tasks[1].key]

    assert ready_item.data(NAME_ROLE) == tasks[0].display_name
    assert ready_item.data(META_ROLE).startswith("MP4")
    assert ready_item.data(STATUS_ROLE) == "已读取"
    assert ready_item.data(STATUS_COLOR_ROLE) == palette.text
    assert ready_item.data(ACCENT_ROLE) == ""

    assert failed_item.data(STATUS_ROLE) == "失败"
    assert failed_item.data(STATUS_COLOR_ROLE) == palette.danger
    assert failed_item.data(ACCENT_ROLE) == palette.danger
    assert failed_item.icon().isNull() is False


def test_footer_tracks_overall_batch_progress(
    qtbot,
    tmp_path,
    isolated_settings,
    monkeypatch,
) -> None:
    window, tasks = _window_with_tasks(qtbot, tmp_path, isolated_settings, count=3)
    started: list[str] = []
    monkeypatch.setattr(
        MainWindow,
        "_start_conversion",
        lambda self: (started.append(self._current_task_key()), True)[1],
    )
    _auto_dialogs(window, [task.key for task in tasks])

    window._start_batch_conversion()

    assert "批量 1/3" in window.batch_status_label.text()
    assert window.batch_progress_bar.isVisibleTo(window)

    window._on_conversion_progress(
        ConversionProgress(
            task_key=tasks[0].key,
            percent=40.0,
            processed_seconds=24.0,
            speed="2x",
            eta_seconds=12.0,
        )
    )

    assert "当前 40%" in window.batch_status_label.text()
    assert window.batch_progress_bar.value() == 13

    for task in tasks:
        task.status = TaskStatus.COMPLETED
        window._update_task_item(task)
    window._batch_watchdog.stop()
    window._finish_batch()

    assert window.batch_status_label.isVisibleTo(window) is False
    assert window.batch_progress_bar.isVisibleTo(window) is False


def test_shortcuts_are_registered(qtbot, isolated_settings) -> None:
    window = MainWindow(settings=isolated_settings)
    qtbot.addWidget(window)

    sequences = {shortcut.key().toString() for shortcut in window.shortcuts}

    bindings = [shortcut.key() for shortcut in window.shortcuts]
    assert QKeySequence("Ctrl+O") in bindings
    assert QKeySequence("Delete") in bindings
    assert QKeySequence("Ctrl+Shift+B") in bindings
    assert QKeySequence("Esc") in bindings
    assert QKeySequence("Ctrl+Return") in bindings
    assert sequences  # Qt reports its own canonical text, e.g. "Del"


def test_delete_shortcut_ignores_text_fields(
    qtbot,
    tmp_path,
    isolated_settings,
    monkeypatch,
) -> None:
    window, _tasks = _window_with_tasks(qtbot, tmp_path, isolated_settings)
    removed: list[bool] = []
    monkeypatch.setattr(MainWindow, "_remove_selected_task", lambda self: removed.append(True))

    class TextFocus:
        @staticmethod
        def focusWidget() -> QLineEdit:
            return QLineEdit()

    monkeypatch.setattr("video_switch.ui.main_window.QApplication", TextFocus)
    window._delete_focused_task()
    assert removed == []

    class NoFocus:
        @staticmethod
        def focusWidget() -> None:
            return None

    monkeypatch.setattr("video_switch.ui.main_window.QApplication", NoFocus)
    window._delete_focused_task()
    assert removed == [True]


def test_window_geometry_is_remembered(qtbot, isolated_settings) -> None:
    first = MainWindow(settings=isolated_settings)
    qtbot.addWidget(first)
    first.resize(1180, 760)
    first._save_window_geometry()
    isolated_settings.sync()

    second = MainWindow(settings=isolated_settings)
    qtbot.addWidget(second)

    assert (second.width(), second.height()) == (1180, 760)


def test_delegate_leaves_only_the_background_to_the_style(
    qtbot,
    tmp_path,
    isolated_settings,
) -> None:
    """Text and icon must be cleared, or the style paints a second overlapping icon."""
    window, tasks = _window_with_tasks(qtbot, tmp_path, isolated_settings, count=1)
    window.show()
    qtbot.waitExposed(window)
    item = window.task_items[tasks[0].key]
    index = window.task_list.indexFromItem(item)
    option = QStyleOptionViewItem()
    option.rect = window.task_list.visualItemRect(item)
    delegate: TaskItemDelegate = window.task_list.itemDelegate()

    prepared = delegate._background_option(option, index)

    assert prepared.text == ""
    assert prepared.icon.isNull() is True
