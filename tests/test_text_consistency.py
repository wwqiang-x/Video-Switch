"""Tests for step 10 batch two: wording, numbers, punctuation and control states."""

from pathlib import Path

from PySide6.QtWidgets import QPushButton, QSizePolicy

from video_switch.formatting import format_duration, format_speed
from video_switch.models.media_info import MediaInfo
from video_switch.models.media_task import TaskStatus
from video_switch.services.history_store import ConversionHistoryStore
from video_switch.ui.batch_dialogs import BatchConfirmDialog
from video_switch.ui.format_help_dialog import FormatHelpDialog
from video_switch.ui.main_window import ACTION_BUTTON_MIN_WIDTH, MainWindow


def _window(qtbot, tmp_path, isolated_settings, count: int = 2):
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
        task.media_info = MediaInfo(duration_seconds=90.0, width=1280, height=720)
        task.status = TaskStatus.METADATA_READY
        window._update_task_item(task)
    window._available_ffmpeg_path = lambda: Path("ffmpeg.exe")
    return window, tasks


def test_duration_format_is_shared_everywhere() -> None:
    for seconds in (0, 7, 59, 60, 88, 3599, 3600, 3700, 7325):
        assert MediaInfo(duration_seconds=seconds).duration_text == format_duration(seconds)

    assert format_duration(None) == "--"
    assert format_duration(88) == "01:28"
    assert format_duration(3725) == "01:02:05"


def test_speed_uses_the_multiplication_sign() -> None:
    assert format_speed("1.24x") == "1.24×"
    assert format_speed(" 12X ") == "12×"
    assert format_speed("N/A") == "N/A"
    assert format_speed(None) == ""


def test_loading_messages_use_the_ellipsis_character(qtbot, isolated_settings) -> None:
    window = MainWindow(settings=isolated_settings)
    qtbot.addWidget(window)

    assert window.footer_status_label.text().endswith("…")
    assert "..." not in window.footer_status_label.text()


def test_empty_state_wording_is_consistent(qtbot, isolated_settings) -> None:
    window = MainWindow(settings=isolated_settings)
    qtbot.addWidget(window)

    assert window.media_status.text() == "尚未选择"
    assert window.source_path.text() == "尚未导入视频"


def test_info_dialogs_close_with_the_same_button(qtbot) -> None:
    dialog = FormatHelpDialog()
    qtbot.addWidget(dialog)

    texts = {button.text() for button in dialog.findChildren(QPushButton)}

    assert "关闭" in texts
    assert "知道了" not in texts


def test_batch_confirm_dialog_offers_a_step_back(qtbot) -> None:
    dialog = BatchConfirmDialog(2, [("输出格式", "MP4")], "D:\\video end")
    qtbot.addWidget(dialog)

    texts = {button.text() for button in dialog.findChildren(QPushButton)}

    assert texts == {"上一步", "开始转换"}


def test_clear_queue_dialog_matches_the_button_wording(
    qtbot,
    tmp_path,
    isolated_settings,
    monkeypatch,
) -> None:
    window, _tasks = _window(qtbot, tmp_path, isolated_settings)
    captured: dict[str, str] = {}
    original = MainWindow._warning_dialog

    def capture(self, title: str, text: str):
        captured["title"] = title
        captured["text"] = text
        dialog = original(self, title, text)
        dialog.exec = lambda: None  # keep the test headless
        return dialog

    monkeypatch.setattr(MainWindow, "_warning_dialog", capture)

    window._clear_queue()

    assert captured["title"] == "清空任务"
    assert "清空队列中的 2 个任务" in captured["text"]


def test_action_buttons_keep_a_stable_width(qtbot, tmp_path, isolated_settings) -> None:
    window, _tasks = _window(qtbot, tmp_path, isolated_settings)

    for button in (window.batch_button, window.retry_button, window.cancel_button):
        # Fixed policy ties the width to the label, so showing or hiding the retry
        # button no longer resizes its neighbours, at any scaling factor.
        assert button.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Fixed
        assert button.minimumWidth() == ACTION_BUTTON_MIN_WIDTH


def test_disabled_inputs_have_a_dedicated_style(qtbot, isolated_settings) -> None:
    window = MainWindow(settings=isolated_settings)
    qtbot.addWidget(window)

    sheet = window.styleSheet()
    for selector in (
        "QLineEdit:disabled",
        "QComboBox:disabled",
        "QSpinBox:disabled",
        "QCheckBox:disabled",
    ):
        assert selector in sheet
