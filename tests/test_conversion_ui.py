"""Tests for conversion settings UI behavior."""

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
