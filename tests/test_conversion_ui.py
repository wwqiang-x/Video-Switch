"""Tests for conversion settings UI behavior."""

from video_switch.models.conversion_history import ConversionHistoryRecord
from video_switch.models.media_info import MediaInfo
from video_switch.models.media_task import TaskStatus
from video_switch.services.conversion_runner import (
    ConversionProgress,
    ConversionResult,
    ConversionRunner,
)
from video_switch.services.history_store import ConversionHistoryStore
from video_switch.ui.main_window import MainWindow, _progress_percent


def test_default_conversion_command_is_mp4(qtbot, isolated_settings) -> None:
    window = MainWindow(settings=isolated_settings)
    qtbot.addWidget(window)

    assert window.format_buttons["MP4"].isChecked()
    assert window.output_name_preview.text().endswith(".mp4")
    assert "libx264" in window.command_preview.toPlainText()
    assert "+faststart" in window.command_preview.toPlainText()


def test_webm_format_updates_codecs_and_command(
    qtbot,
    isolated_settings,
) -> None:
    window = MainWindow(settings=isolated_settings)
    qtbot.addWidget(window)

    window.format_buttons["WebM"].click()

    assert window.video_codec_combo.currentText() == "VP9"
    assert window.audio_codec_combo.currentText() == "Opus"
    assert "libvpx-vp9" in window.command_preview.toPlainText()
    assert "libopus" in window.command_preview.toPlainText()
    assert window.output_name_preview.text().endswith(".webm")


def test_mp3_disables_video_controls(qtbot, isolated_settings) -> None:
    window = MainWindow(settings=isolated_settings)
    qtbot.addWidget(window)

    window.format_buttons["MP3"].click()

    assert window.video_codec_combo.isEnabled() is False
    assert window.resolution_combo.isEnabled() is False
    assert window.frame_rate_combo.isEnabled() is False
    assert window.quality_combo.currentText() == "不适用"
    assert window.resolution_combo.currentText() == "不适用"
    assert window.frame_rate_combo.currentText() == "不适用"
    assert window.crf_spin.value() == 0
    assert window.keep_audio_checkbox.isChecked() is True
    assert window.keep_audio_checkbox.isEnabled() is False
    assert window.audio_bitrate_combo.currentText() == "192 kbps"
    assert "-vn" in window.command_preview.toPlainText()
    assert "libmp3lame" in window.command_preview.toPlainText()


def test_audio_only_values_do_not_leak_back_to_mp4(
    qtbot,
    isolated_settings,
) -> None:
    window = MainWindow(settings=isolated_settings)
    qtbot.addWidget(window)
    window.resolution_combo.setCurrentText("1080p")
    window.frame_rate_combo.setCurrentText("60 FPS")
    window.quality_combo.setCurrentText("高质量")

    window.format_buttons["MP3"].click()

    assert window.resolution_combo.currentText() == "不适用"
    assert window.frame_rate_combo.currentText() == "不适用"
    assert window.quality_combo.currentText() == "不适用"

    window.format_buttons["MP4"].click()

    assert window.resolution_combo.currentText() == "保持原始"
    assert window.frame_rate_combo.currentText() == "保持原始"
    assert window.quality_combo.currentText() == "平衡（推荐）"
    assert window.crf_spin.value() == 23


def test_wav_hides_audio_bitrate(qtbot, isolated_settings) -> None:
    window = MainWindow(settings=isolated_settings)
    qtbot.addWidget(window)

    window.format_buttons["WAV"].click()

    assert window.audio_bitrate_combo.currentText() == "不适用"
    assert window.audio_bitrate_combo.isEnabled() is False
    assert window.command_preview.toPlainText().find("-b:a") == -1


def test_custom_output_directory_updates_preview(
    qtbot,
    tmp_path,
    isolated_settings,
) -> None:
    window = MainWindow(settings=isolated_settings)
    qtbot.addWidget(window)
    output_directory = tmp_path / "exports"
    output_directory.mkdir()

    window.output_directory = output_directory
    window._update_output_preview()

    assert window.output_path.text() == str(output_directory)
    assert str(output_directory) in window.command_preview.toPlainText()


def test_conversion_settings_persist(
    qtbot,
    isolated_settings,
) -> None:
    first_window = MainWindow(settings=isolated_settings)
    qtbot.addWidget(first_window)
    first_window.format_buttons["WebM"].click()
    first_window.quality_combo.setCurrentText("高质量")
    isolated_settings.sync()

    second_window = MainWindow(settings=isolated_settings)
    qtbot.addWidget(second_window)

    assert second_window.format_buttons["WebM"].isChecked()
    assert second_window.quality_combo.currentText() == "高质量"
    assert second_window.crf_spin.value() == 18


def test_imported_tasks_restore_from_settings(
    qtbot,
    tmp_path,
    isolated_settings,
) -> None:
    video = tmp_path / "restored.mp4"
    video.write_bytes(b"video")
    first_window = MainWindow(settings=isolated_settings)
    qtbot.addWidget(first_window)
    first_window._import_paths([str(video)])
    isolated_settings.sync()

    second_window = MainWindow(settings=isolated_settings)
    qtbot.addWidget(second_window)
    second_window._restore_saved_tasks()

    assert len(second_window.tasks) == 1
    restored_task = next(iter(second_window.tasks.values()))
    assert restored_task.path == video.resolve()


def _cancelled_task_window(qtbot, tmp_path, isolated_settings, name="clip.mp4"):
    video = tmp_path / name
    video.write_bytes(b"video")
    window = MainWindow(settings=isolated_settings)
    qtbot.addWidget(window)
    window._import_paths([str(video)], show_feedback=False)
    task = next(iter(window.tasks.values()))
    task.media_info = MediaInfo(duration_seconds=120.0, width=1920, height=1080)
    task.status = TaskStatus.CANCELLED
    window._apply_task_to_preview(task)
    return window, task


def test_cancelled_task_shows_resume_and_clear_state_buttons(
    qtbot,
    tmp_path,
    isolated_settings,
) -> None:
    window, task = _cancelled_task_window(qtbot, tmp_path, isolated_settings)

    assert window.resume_conversion_button.isVisibleTo(window)
    assert window.clear_state_button.isVisibleTo(window)
    assert window.resume_conversion_button.text() == "重新转换"

    task.conversion_resumable = True
    window._apply_task_to_preview(task)

    assert window.resume_conversion_button.text() == "继续转换"
    assert "继续" in window.resume_conversion_button.toolTip()


def test_resume_conversion_keeps_resumable_progress(
    qtbot,
    tmp_path,
    isolated_settings,
) -> None:
    window, task = _cancelled_task_window(qtbot, tmp_path, isolated_settings)
    task.conversion_resumable = True
    task.conversion_progress = 62.0

    window._resume_conversion()

    assert task.status == TaskStatus.METADATA_READY
    assert task.conversion_progress == 62.0


def test_resume_conversion_resets_progress_when_not_resumable(
    qtbot,
    tmp_path,
    isolated_settings,
) -> None:
    window, task = _cancelled_task_window(qtbot, tmp_path, isolated_settings)
    task.conversion_resumable = False
    task.conversion_progress = 40.0

    window._resume_conversion()

    assert task.conversion_progress == 0.0


def test_clear_conversion_state_removes_parts_and_resets_task(
    qtbot,
    tmp_path,
    isolated_settings,
) -> None:
    window, task = _cancelled_task_window(qtbot, tmp_path, isolated_settings)
    part_dir = tmp_path / "converted" / ".clip.abc.parts"
    part_dir.mkdir(parents=True)
    (part_dir / "part_00000.mp4").write_bytes(b"segment")
    task.conversion_part_dir = part_dir
    task.conversion_parts_completed = 1
    task.conversion_settings_key = "abc"
    task.conversion_resumable = True
    task.conversion_progress = 30.0
    task.conversion_error = "转换已取消"
    window._apply_task_to_preview(task)
    window._confirm_discard_progress = lambda _task: True

    window._clear_conversion_state()

    assert task.status == TaskStatus.METADATA_READY
    assert task.conversion_part_dir is None
    assert task.conversion_parts_completed == 0
    assert task.conversion_settings_key == ""
    assert task.conversion_resumable is False
    assert task.conversion_progress == 0.0
    assert task.conversion_error is None
    assert part_dir.exists() is False
    assert window.clear_state_button.isVisibleTo(window) is False


def test_clear_conversion_state_keeps_parts_when_user_declines(
    qtbot,
    tmp_path,
    isolated_settings,
) -> None:
    window, task = _cancelled_task_window(qtbot, tmp_path, isolated_settings)
    part_dir = tmp_path / "converted" / ".clip.abc.parts"
    part_dir.mkdir(parents=True)
    (part_dir / "part_00000.mp4").write_bytes(b"segment")
    task.conversion_part_dir = part_dir
    task.conversion_parts_completed = 1
    task.conversion_resumable = True
    task.conversion_progress = 45.0
    task.conversion_error = "转换已取消"
    window._apply_task_to_preview(task)
    window._confirm_discard_progress = lambda _task: False

    window._clear_conversion_state()

    assert task.status == TaskStatus.CANCELLED
    assert task.conversion_resumable is True
    assert task.conversion_part_dir == part_dir
    assert part_dir.is_dir()
    assert window.clear_state_button.isVisibleTo(window)


def test_clear_conversion_state_skips_confirmation_without_segments(
    qtbot,
    tmp_path,
    isolated_settings,
) -> None:
    window, task = _cancelled_task_window(qtbot, tmp_path, isolated_settings)
    task.conversion_resumable = True
    task.conversion_parts_completed = 0
    task.conversion_progress = 0.0
    window._apply_task_to_preview(task)

    def fail(_task) -> bool:
        raise AssertionError("confirmation should not be asked")

    window._confirm_discard_progress = fail

    window._clear_conversion_state()

    assert task.status == TaskStatus.METADATA_READY
    assert task.conversion_resumable is False


def test_cancelled_detail_shows_kept_progress(
    qtbot,
    tmp_path,
    isolated_settings,
) -> None:
    window, task = _cancelled_task_window(qtbot, tmp_path, isolated_settings)
    task.conversion_resumable = True
    task.conversion_parts_completed = 1
    task.conversion_progress = 43.0

    window._apply_task_to_preview(task)

    assert "43%" in window.conversion_detail_label.text()


def test_cancelled_detail_without_finished_segments(
    qtbot,
    tmp_path,
    isolated_settings,
) -> None:
    window, task = _cancelled_task_window(qtbot, tmp_path, isolated_settings)
    task.conversion_resumable = True
    task.conversion_parts_completed = 0
    task.conversion_progress = 0.0

    window._apply_task_to_preview(task)

    assert window.conversion_detail_label.text() == "可继续转换"


def test_delete_state_button_sits_at_the_row_end(
    qtbot,
    tmp_path,
    isolated_settings,
) -> None:
    window, task = _cancelled_task_window(qtbot, tmp_path, isolated_settings)
    window.show()
    qtbot.waitExposed(window)

    frame = window.conversion_progress_frame
    button = window.clear_state_button

    assert button.isVisibleTo(window)
    assert button.geometry().right() >= frame.width() - 20
    assert button.geometry().left() > window.resume_conversion_button.geometry().right()


def test_converting_row_shows_remaining_time_on_the_right(
    qtbot,
    tmp_path,
    isolated_settings,
) -> None:
    window, task = _cancelled_task_window(qtbot, tmp_path, isolated_settings)
    task.status = TaskStatus.CONVERTING
    task.conversion_speed = "1.2x"
    task.conversion_eta_seconds = 88.0
    window._apply_task_to_preview(task)
    window.show()
    qtbot.waitExposed(window)

    detail = window.conversion_detail_label
    assert detail.width() > 0
    assert "剩余 01:28" in detail.text()
    assert detail.x() + detail.width() > window.conversion_progress_bar.width() / 2


def test_cancelled_conversion_result_keeps_progress(
    qtbot,
    tmp_path,
    isolated_settings,
) -> None:
    window, task = _cancelled_task_window(qtbot, tmp_path, isolated_settings)
    window.history_store = ConversionHistoryStore(tmp_path / "history.json")
    result = ConversionResult(
        task_key=task.key,
        source_key=task.content_signature,
        source_path=task.path,
        output_format="MP4",
        output_path=tmp_path / "converted" / "clip_converted.mp4",
        success=False,
        cancelled=True,
        error="转换已取消",
        log="",
        elapsed_seconds=12.0,
        can_resume=True,
        progress_percent=58.0,
    )

    window._on_conversion_finished(result)

    assert task.status == TaskStatus.CANCELLED
    assert task.conversion_progress == 58.0
    assert task.conversion_resumable is True


def _completed_task_window(qtbot, tmp_path, isolated_settings):
    window, task = _cancelled_task_window(qtbot, tmp_path, isolated_settings)
    output = tmp_path / "converted" / "clip_converted.mkv"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(b"converted output")
    task.status = TaskStatus.COMPLETED
    task.output_path = output
    task.conversion_format = "MKV"
    task.conversion_summary = "MKV · H.264"
    task.conversion_progress = 100.0
    window._apply_task_to_preview(task)
    return window, task, output


def test_completed_task_shows_clear_state_button_at_row_end(
    qtbot,
    tmp_path,
    isolated_settings,
) -> None:
    window, task, _output = _completed_task_window(qtbot, tmp_path, isolated_settings)
    window.show()
    qtbot.waitExposed(window)

    button = window.clear_state_button
    frame = window.conversion_progress_frame

    assert button.isVisibleTo(window)
    assert "清除完成状态" in button.toolTip()
    assert button.geometry().right() >= frame.width() - 20
    assert button.geometry().left() > window.open_folder_button.geometry().right()
    assert window.resume_conversion_button.isVisibleTo(window) is False


def test_clear_conversion_state_keeps_the_output_file(
    qtbot,
    tmp_path,
    isolated_settings,
) -> None:
    window, task, output = _completed_task_window(qtbot, tmp_path, isolated_settings)

    window._clear_conversion_state()

    assert task.status == TaskStatus.METADATA_READY
    assert task.output_path is None
    assert task.conversion_progress == 0.0
    assert task.conversion_summary is None
    assert task.conversion_format is None
    assert output.is_file()
    assert window.clear_state_button.isVisibleTo(window) is False
    assert window.open_file_button.isVisibleTo(window) is False


def test_completed_task_clear_skips_confirmation(
    qtbot,
    tmp_path,
    isolated_settings,
) -> None:
    window, _task, _output = _completed_task_window(qtbot, tmp_path, isolated_settings)

    def fail(_task) -> bool:
        raise AssertionError("confirmation should not be asked")

    window._confirm_discard_progress = fail

    window._clear_conversion_state()


def test_cancel_updates_the_row_immediately(
    qtbot,
    tmp_path,
    isolated_settings,
    monkeypatch,
) -> None:
    window, task = _cancelled_task_window(qtbot, tmp_path, isolated_settings)
    task.status = TaskStatus.CONVERTING
    window._apply_task_to_preview(task)
    cancelled: list[bool] = []
    monkeypatch.setattr(ConversionRunner, "is_running", property(lambda self: True))
    monkeypatch.setattr(ConversionRunner, "cancel", lambda self: cancelled.append(True))
    try:
        window._cancel_conversion()
    finally:
        # Leaving is_running True would make the close-while-running dialog pop
        # up during widget teardown and block the suite.
        monkeypatch.undo()

    assert window.conversion_status_label.text() == "正在取消"
    assert window.cancel_button.isEnabled() is False
    assert cancelled == [True]


def test_audio_only_format_never_leaks_placeholders_into_settings(
    qtbot,
    tmp_path,
    isolated_settings,
) -> None:
    """MP3 disables resolution and frame rate; the estimate must still work."""
    window, task = _cancelled_task_window(qtbot, tmp_path, isolated_settings)

    window.format_buttons["MP3"].click()
    settings = window._current_conversion_settings()

    assert window.resolution_combo.currentText() == "不适用"
    assert settings.resolution == "保持原始"
    assert settings.frame_rate == "保持原始"

    window._apply_task_to_preview(task)

    assert "约" in window.duration_estimate_label.text()


def test_history_panel_follows_the_selected_task(
    qtbot,
    tmp_path,
    isolated_settings,
) -> None:
    window = MainWindow(settings=isolated_settings)
    qtbot.addWidget(window)
    window.history_store = ConversionHistoryStore(tmp_path / "history.json")
    window.history_records = []
    first = tmp_path / "first.mp4"
    second = tmp_path / "second.mp4"
    first.write_bytes(b"first video")
    second.write_bytes(b"second video")
    window._import_paths([str(first), str(second)], show_feedback=False, persist=False)
    tasks = window._tasks_in_list_order()
    window.history_records = [
        ConversionHistoryRecord(
            record_id="r1",
            timestamp="2026-10-12T22:45:16+08:00",
            source_key=tasks[0].content_signature,
            source_path=tasks[0].path,
            output_path=tmp_path / "first_converted.mp4",
            output_format="MP4",
            status="已完成",
            error=None,
            file_size=10,
            elapsed_seconds=1.0,
        )
    ]
    window._refresh_history_list()

    window.task_list.setCurrentItem(window.task_items[tasks[0].key])

    assert window.history_section.title_label.text().endswith("first.mp4")
    assert window.history_list.count() == 1
    assert window.history_section.isVisibleTo(window) is True

    window.task_list.setCurrentItem(window.task_items[tasks[1].key])

    assert window.history_section.title_label.text().endswith("second.mp4")
    assert window.history_list.count() == 0
    assert window.history_section.isVisibleTo(window) is False


def test_history_panel_is_bound_before_the_preview_is_built(
    qtbot,
    tmp_path,
    isolated_settings,
    monkeypatch,
) -> None:
    """History switches first, so a later preview failure cannot leave it stale."""
    window = MainWindow(settings=isolated_settings)
    qtbot.addWidget(window)
    window.history_store = ConversionHistoryStore(tmp_path / "history.json")
    window.history_records = []
    first = tmp_path / "first.mp4"
    second = tmp_path / "second.mp4"
    first.write_bytes(b"first video")
    second.write_bytes(b"second video")
    window._import_paths([str(first), str(second)], show_feedback=False, persist=False)
    tasks = window._tasks_in_list_order()
    window.history_records = [
        ConversionHistoryRecord(
            record_id="r1",
            timestamp="2026-10-12T22:45:16+08:00",
            source_key=tasks[0].content_signature,
            source_path=tasks[0].path,
            output_path=tmp_path / "first_converted.mp4",
            output_format="MP4",
            status="已完成",
            error=None,
            file_size=10,
            elapsed_seconds=1.0,
        )
    ]
    window._refresh_history_list()
    window.task_list.setCurrentItem(window.task_items[tasks[0].key])

    observed: list[str] = []

    def record_title(self: MainWindow) -> None:
        observed.append(window.history_section.title_label.text())

    monkeypatch.setattr(MainWindow, "_update_output_preview", record_title)

    window.task_list.setCurrentItem(window.task_items[tasks[1].key])

    assert observed
    assert observed[-1].endswith("second.mp4")
    assert window.history_section.title_label.text().endswith("second.mp4")
    assert window.history_list.count() == 0


def test_progress_percent_is_clamped() -> None:
    assert _progress_percent(-230584300921369.38) == 0
    assert _progress_percent(float("inf")) == 100
    assert _progress_percent(float("-inf")) == 0
    assert _progress_percent(float("nan")) == 0
    assert _progress_percent(41.6) == 42


def test_bogus_progress_signal_does_not_break_the_progress_bar(
    qtbot,
    tmp_path,
    isolated_settings,
) -> None:
    window, task = _cancelled_task_window(qtbot, tmp_path, isolated_settings)
    task.status = TaskStatus.CONVERTING
    window._apply_task_to_preview(task)

    window._on_conversion_progress(
        ConversionProgress(
            task_key=task.key,
            percent=-230584300921369.38,
            processed_seconds=-9223372036854.775,
            speed="N/A",
            eta_seconds=None,
        )
    )

    assert task.conversion_progress == 0.0
    assert window.conversion_progress_bar.value() == 0
