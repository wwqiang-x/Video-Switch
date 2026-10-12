"""Tests for conversion settings UI behavior."""

from video_switch.models.media_info import MediaInfo
from video_switch.models.media_task import TaskStatus
from video_switch.services.conversion_runner import ConversionResult
from video_switch.services.history_store import ConversionHistoryStore
from video_switch.ui.main_window import MainWindow


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


def test_clear_cancelled_state_removes_parts_and_resets_task(
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

    window._clear_cancelled_state()

    assert task.status == TaskStatus.METADATA_READY
    assert task.conversion_part_dir is None
    assert task.conversion_parts_completed == 0
    assert task.conversion_settings_key == ""
    assert task.conversion_resumable is False
    assert task.conversion_progress == 0.0
    assert task.conversion_error is None
    assert part_dir.exists() is False
    assert window.clear_state_button.isVisibleTo(window) is False


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
