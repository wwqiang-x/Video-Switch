"""Tests for validating and importing video files."""

from pathlib import Path

from video_switch.services.video_importer import VideoImporter, format_file_size


def test_import_supported_video_with_spaces(tmp_path: Path) -> None:
    video = tmp_path / "中文 示例视频.mp4"
    video.write_bytes(b"0" * 1536)

    result = VideoImporter().import_paths([str(video)])

    assert len(result.added) == 1
    assert result.added[0].display_name == "中文 示例视频.mp4"
    assert result.added[0].extension == "MP4"
    assert result.added[0].size_bytes == 1536
    assert result.duplicates == []
    assert result.issues == []


def test_import_ignores_duplicate_video(tmp_path: Path) -> None:
    video = tmp_path / "duplicate.mkv"
    video.write_bytes(b"video")
    importer = VideoImporter()

    first = importer.import_paths([str(video)])
    second = importer.import_paths(
        [str(video)],
        existing_keys={task.key for task in first.added},
    )

    assert len(first.added) == 1
    assert second.added == []
    assert second.duplicates == [video.resolve()]


def test_import_reports_unsupported_and_missing_files(tmp_path: Path) -> None:
    unsupported = tmp_path / "notes.txt"
    unsupported.write_text("not a video", encoding="utf-8")
    missing = tmp_path / "missing.mp4"

    result = VideoImporter().import_paths([str(unsupported), str(missing)])

    assert result.added == []
    assert len(result.issues) == 2
    assert {issue.reason for issue in result.issues} == {
        "不支持该文件格式",
        "文件不存在或无法访问",
    }


def test_format_file_size() -> None:
    assert format_file_size(512) == "512 B"
    assert format_file_size(1536) == "1.5 KB"
    assert format_file_size(2 * 1024 * 1024) == "2.0 MB"
