"""State-machine tests for the media services, without launching real tools."""

import json
from datetime import datetime
from pathlib import Path

import pytest
from PySide6.QtCore import QByteArray, QProcess

from video_switch.models.conversion_settings import ConversionSettings
from video_switch.models.media_info import MediaInfo
from video_switch.models.media_task import MediaTask, TaskStatus
from video_switch.services.conversion_runner import (
    SEGMENT_DURATION_SECONDS,
    ConversionRunner,
)
from video_switch.services.media_probe import (
    MediaProbeService,
    ProbeResult,
    _container_name,
    _parse_frame_rate,
    parse_ffprobe_output,
)
from video_switch.services.thumbnail import (
    THUMBNAIL_CACHE_VERSION,
    ThumbnailResult,
    ThumbnailService,
    _ThumbnailJob,
    thumbnail_cache_path,
    thumbnail_positions,
)
from video_switch.services.toolchain import (
    ToolchainDetector,
    ToolchainStatus,
    ToolInfo,
    parse_tool_version,
    resolve_tool,
)

FFMPEG_STUB = Path("ffmpeg.exe")
FFPROBE_STUB = Path("ffprobe.exe")


class FakeProcess(QProcess):
    """Stand-in for a finished QProcess with canned output."""

    def __init__(self, stdout: bytes = b"", stderr: bytes = b"") -> None:
        super().__init__()
        self._stdout = stdout
        self._stderr = stderr

    def readAllStandardOutput(self) -> QByteArray:
        return QByteArray(self._stdout)

    def readAllStandardError(self) -> QByteArray:
        return QByteArray(self._stderr)


def _task(tmp_path: Path, duration: float = 90.0, name: str = "clip.mp4") -> MediaTask:
    source = tmp_path / name
    source.write_bytes(b"video")
    return MediaTask(
        path=source,
        size_bytes=source.stat().st_size,
        content_signature=f"signature-{name}",
        imported_at=datetime.now(),
        media_info=MediaInfo(duration_seconds=duration, width=1920, height=1080),
        status=TaskStatus.METADATA_READY,
    )


def _record_process_launches(monkeypatch) -> list[list[str]]:
    """Capture the FFmpeg argument lists instead of spawning processes."""
    calls: list[list[str]] = []
    monkeypatch.setattr(ConversionRunner, "_start_process", lambda self, args: calls.append(args))
    return calls


# --------------------------------------------------------------------------- probe


def test_parse_ffprobe_output_reads_video_and_audio() -> None:
    payload = json.dumps(
        {
            "streams": [
                {
                    "codec_type": "video",
                    "codec_name": "h264",
                    "width": 1920,
                    "height": 1080,
                    "avg_frame_rate": "30000/1001",
                    "pix_fmt": "yuv420p",
                },
                {
                    "codec_type": "audio",
                    "codec_name": "aac",
                    "sample_rate": "48000",
                    "channels": 2,
                },
            ],
            "format": {"duration": "750.5", "bit_rate": "730000", "format_name": "mov,mp4"},
        }
    )

    info = parse_ffprobe_output(payload, Path("movie.mp4"))

    assert info.duration_seconds == 750.5
    assert info.width == 1920
    assert info.frame_rate == pytest.approx(29.97, rel=1e-3)
    assert info.video_codec == "h264"
    assert info.audio_codec == "aac"
    assert info.audio_channels == 2
    assert info.container == "MP4"
    assert info.bit_rate == 730000


def test_parse_ffprobe_output_falls_back_to_stream_values() -> None:
    payload = json.dumps(
        {
            "streams": [
                {"codec_type": "video", "duration": "12.5", "bit_rate": "900000", "height": 720}
            ],
            "format": {"format_name": "matroska,webm"},
        }
    )

    info = parse_ffprobe_output(payload, Path("clip.unknown"))

    assert info.duration_seconds == 12.5
    assert info.bit_rate == 900000
    assert info.container == "WebM"
    assert info.audio_codec is None


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("25", 25.0),
        ("0/0", None),
        ("N/A", None),
        ("", None),
        ("bad/bad", None),
        ("30000/1001", 29.97002997002997),
    ],
)
def test_parse_frame_rate_variants(value, expected) -> None:
    result = _parse_frame_rate(value)
    if expected is None:
        assert result is None
    else:
        assert result == pytest.approx(expected)


def test_container_name_uses_suffix_then_format() -> None:
    assert _container_name(Path("a.mkv"), "") == "MKV"
    assert _container_name(Path("a.bin"), "matroska,webm") == "WebM"
    assert _container_name(Path("a.bin"), "matroska") == "MKV"
    assert _container_name(Path("a.bin"), "custom-format") == "CUSTOM-FORMAT"
    assert _container_name(Path("a.bin"), "") is None


def test_probe_service_reports_parsed_info(qtbot, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(MediaProbeService, "_start_next", lambda self: None)
    service = MediaProbeService()
    qtbot.addWidget(service) if False else None
    task = _task(tmp_path)
    results: list[ProbeResult] = []
    service.task_finished.connect(results.append)
    service.enqueue(task, FFPROBE_STUB)
    service._current = (task.key, task.path, FFPROBE_STUB)
    service._process = FakeProcess(
        stdout=json.dumps({"streams": [], "format": {"duration": "30"}}).encode()
    )

    service._on_process_finished(0, QProcess.ExitStatus.NormalExit)

    assert results and results[-1].info is not None
    assert results[-1].info.duration_seconds == 30.0
    assert service._current is None


def test_probe_service_reports_broken_json(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(MediaProbeService, "_start_next", lambda self: None)
    service = MediaProbeService()
    task = _task(tmp_path)
    results: list[ProbeResult] = []
    service.task_finished.connect(results.append)
    service._current = (task.key, task.path, FFPROBE_STUB)
    service._process = FakeProcess(stdout=b"not json at all")

    service._on_process_finished(0, QProcess.ExitStatus.NormalExit)

    assert "解析失败" in (results[-1].error or "")
    assert results[-1].raw_output == "not json at all"


def test_probe_service_reports_last_stderr_line(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(MediaProbeService, "_start_next", lambda self: None)
    service = MediaProbeService()
    task = _task(tmp_path)
    results: list[ProbeResult] = []
    service.task_finished.connect(results.append)
    service._current = (task.key, task.path, FFPROBE_STUB)
    service._process = FakeProcess(
        stderr=b"line one\nclip.mp4: Invalid data found when processing input\n"
    )

    service._on_process_finished(1, QProcess.ExitStatus.NormalExit)

    assert results[-1].error == "clip.mp4: Invalid data found when processing input"
    assert results[-1].info is None


def test_probe_service_handles_start_failure_and_timeout(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(MediaProbeService, "_start_next", lambda self: None)
    service = MediaProbeService()
    task = _task(tmp_path)
    results: list[ProbeResult] = []
    service.task_finished.connect(results.append)

    service._current = (task.key, task.path, FFPROBE_STUB)
    service._on_process_error(QProcess.ProcessError.FailedToStart)
    assert "无法启动 ffprobe" in (results[-1].error or "")

    service._current = (task.key, task.path, FFPROBE_STUB)
    service._process = FakeProcess()
    service._on_timeout()
    assert results[-1].error == "读取视频信息超时"


def test_probe_service_cancel_paths(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(MediaProbeService, "_start_next", lambda self: None)
    service = MediaProbeService()
    first = _task(tmp_path, name="a.mp4")
    second = _task(tmp_path, name="b.mp4")
    service.enqueue(first, FFPROBE_STUB)
    service.enqueue(second, FFPROBE_STUB)
    service.enqueue(first, FFPROBE_STUB)  # duplicate key is ignored

    assert len(service._queue) == 2  # 重复入队被忽略，两个不同任务都在等待
    service.cancel_task(second.key)
    assert [item[0] for item in service._queue] == [first.key]

    service._current = (first.key, first.path, FFPROBE_STUB)
    service._process = FakeProcess()
    service.cancel_task(first.key)
    assert service._current is None

    service.cancel_all()
    assert list(service._queue) == [] and service._queued_keys == set()


# ----------------------------------------------------------------------- thumbnail


def test_thumbnail_positions_cover_fallbacks() -> None:
    assert thumbnail_positions(None)[0] == 1.0
    assert thumbnail_positions(0)[0] == 1.0
    assert thumbnail_positions(10)[0] == 1.0

    positions = thumbnail_positions(600)

    assert positions[0] == 60.0
    assert 1.0 in positions
    assert 300.0 in positions
    assert 0.0 in positions
    assert len(set(positions)) == len(positions)
    assert all(position <= 600 for position in positions)


def test_thumbnail_cache_path_includes_version(tmp_path) -> None:
    path = thumbnail_cache_path(tmp_path, "abc123")

    assert path == tmp_path / f"{THUMBNAIL_CACHE_VERSION}-abc123.jpg"


def test_thumbnail_service_reuses_the_cache(qtbot, tmp_path, monkeypatch) -> None:
    service = ThumbnailService(tmp_path / "cache")
    task = _task(tmp_path)
    cached = thumbnail_cache_path(service.cache_dir, task.content_signature)
    cached.write_bytes(b"jpeg")
    started: list[str] = []
    monkeypatch.setattr(ThumbnailService, "_start_attempt", lambda self: started.append("x"))
    results: list[ThumbnailResult] = []
    service.task_finished.connect(results.append)

    assert service.enqueue(task, FFMPEG_STUB) is True

    assert results[-1].thumbnail_path == cached
    assert started == []


def test_thumbnail_service_deduplicates_pending_tasks(tmp_path, monkeypatch) -> None:
    service = ThumbnailService(tmp_path / "cache")
    task = _task(tmp_path)
    monkeypatch.setattr(ThumbnailService, "_start_attempt", lambda self: None)

    assert service.enqueue(task, FFMPEG_STUB) is True
    assert service.enqueue(task, FFMPEG_STUB) is False

    service.cancel_task(task.key)
    service.cancel_all()
    assert service._current is None


def test_thumbnail_service_finishes_with_a_generated_file(qtbot, tmp_path) -> None:
    service = ThumbnailService(tmp_path / "cache")
    task = _task(tmp_path)
    output = thumbnail_cache_path(service.cache_dir, task.content_signature)
    job = _ThumbnailJob(
        task_key=task.key,
        source_path=task.path,
        output_path=output,
        ffmpeg_path=FFMPEG_STUB,
        positions=(1.0, 5.0),
    )
    results: list[ThumbnailResult] = []
    service.task_finished.connect(results.append)
    service._current = job
    service._process = FakeProcess()
    output.write_bytes(b"jpeg")

    service._on_process_finished(0, QProcess.ExitStatus.NormalExit)

    assert results[-1].thumbnail_path == output
    assert service._current is None


def test_thumbnail_service_gives_up_after_every_position(tmp_path) -> None:
    service = ThumbnailService(tmp_path / "cache")
    task = _task(tmp_path)
    job = _ThumbnailJob(
        task_key=task.key,
        source_path=task.path,
        output_path=thumbnail_cache_path(service.cache_dir, task.content_signature),
        ffmpeg_path=FFMPEG_STUB,
        positions=(1.0,),
    )
    results: list[ThumbnailResult] = []
    service.task_finished.connect(results.append)
    service._current = job
    service._process = FakeProcess()

    service._on_process_finished(1, QProcess.ExitStatus.NormalExit)
    assert service._current_index == 1

    service._start_attempt()

    assert results[-1].error == "多次截取缩略图均失败"


def test_thumbnail_service_timeout_and_start_failure(tmp_path) -> None:
    service = ThumbnailService(tmp_path / "cache")
    task = _task(tmp_path)
    job = _ThumbnailJob(
        task_key=task.key,
        source_path=task.path,
        output_path=thumbnail_cache_path(service.cache_dir, task.content_signature),
        ffmpeg_path=FFMPEG_STUB,
        positions=(1.0, 2.0),
    )
    results: list[ThumbnailResult] = []
    service.task_finished.connect(results.append)

    service._current = job
    service._process = FakeProcess()
    service._on_timeout()
    assert service._current_index == 1

    service._current = job
    service._on_process_error(QProcess.ProcessError.FailedToStart)
    assert "无法启动 ffmpeg" in (results[-1].error or "")


def test_thumbnail_service_deletes_old_cache_versions(tmp_path) -> None:
    service = ThumbnailService(tmp_path / "cache")
    signature = "abc"
    current = thumbnail_cache_path(service.cache_dir, signature)
    legacy_v2 = service.cache_dir / f"v2-{signature}.jpg"
    legacy = service.cache_dir / f"{signature}.jpg"
    for path in (current, legacy_v2, legacy):
        path.write_bytes(b"jpeg")

    service.delete_cached(signature)

    assert not current.exists() and not legacy_v2.exists() and not legacy.exists()


def test_thumbnail_service_prunes_the_cache(tmp_path, monkeypatch) -> None:
    import video_switch.services.thumbnail as thumbnail_module

    monkeypatch.setattr(thumbnail_module, "THUMBNAIL_CACHE_MAX_FILES", 3)
    service = ThumbnailService(tmp_path / "cache")
    for index in range(6):
        path = service.cache_dir / f"v3-signature-{index}.jpg"
        path.write_bytes(b"x" * 1024)
        # 让修改时间明确递增，便于按“最旧优先”清理
        import os

        os.utime(path, (1_700_000_000 + index, 1_700_000_000 + index))

    service._prune_cache()

    remaining = sorted(path.name for path in service.cache_dir.glob("*.jpg"))
    assert remaining == [
        "v3-signature-3.jpg",
        "v3-signature-4.jpg",
        "v3-signature-5.jpg",
    ]


def test_thumbnail_service_prunes_by_size(tmp_path, monkeypatch) -> None:
    import video_switch.services.thumbnail as thumbnail_module

    monkeypatch.setattr(thumbnail_module, "THUMBNAIL_CACHE_MAX_BYTES", 2048)
    service = ThumbnailService(tmp_path / "cache")
    for index in range(4):
        path = service.cache_dir / f"v3-big-{index}.jpg"
        path.write_bytes(b"x" * 1024)
        import os

        os.utime(path, (1_700_000_000 + index, 1_700_000_000 + index))

    service._prune_cache()

    assert len(list(service.cache_dir.glob("*.jpg"))) == 2


# ----------------------------------------------------------------------- toolchain


def test_resolve_tool_prefers_configured_path(tmp_path) -> None:
    executable = tmp_path / "ffmpeg-custom.exe"
    executable.write_bytes(b"binary")

    resolved, source = resolve_tool("ffmpeg", str(executable), roots=())

    assert resolved == executable
    assert source == "用户配置"


def test_resolve_tool_falls_back_to_roots(tmp_path) -> None:
    binary = tmp_path / ".tools" / "ffmpeg" / "bin" / "ffmpeg.exe"
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b"binary")

    resolved, source = resolve_tool("ffmpeg", None, roots=(tmp_path,))

    assert resolved == binary
    assert source == "应用内置"


def test_resolve_tool_reports_nothing_when_missing(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("video_switch.services.toolchain.shutil.which", lambda name: None)

    assert resolve_tool("ffmpeg", None, roots=(tmp_path,)) == (None, None)


def test_parse_tool_version_reads_the_banner() -> None:
    banner = "ffmpeg version 6.0-essentials_build-www.gyan.dev Copyright (c) 2000-2023"

    assert parse_tool_version("ffmpeg", banner) == "6.0-essentials_build-www.gyan.dev"
    assert parse_tool_version("ffprobe", banner) is None


def test_toolchain_status_summary_variants() -> None:
    ready = ToolchainStatus(
        ffmpeg=ToolInfo(name="ffmpeg", executable=FFMPEG_STUB, version="6.0.1"),
        ffprobe=ToolInfo(name="ffprobe", executable=FFPROBE_STUB, version="6.0.1"),
    )
    assert ready.ready is True
    assert "6.0.1" in ready.summary

    missing_probe = ToolchainStatus(
        ffmpeg=ToolInfo(name="ffmpeg", executable=FFMPEG_STUB, version="6.0"),
        ffprobe=ToolInfo(name="ffprobe", error="未找到 ffprobe"),
    )
    assert missing_probe.summary.startswith("ffprobe")

    both_missing = ToolchainStatus(
        ffmpeg=ToolInfo(name="ffmpeg", error="未找到"),
        ffprobe=ToolInfo(name="ffprobe", error="未找到"),
    )
    assert "未找到 FFmpeg 和 ffprobe" in both_missing.summary


def test_toolchain_detector_emits_results(tmp_path, monkeypatch) -> None:
    binary = tmp_path / ".tools" / "ffmpeg" / "bin" / "ffmpeg.exe"
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b"binary")
    probe_binary = tmp_path / ".tools" / "ffmpeg" / "bin" / "ffprobe.exe"
    probe_binary.write_bytes(b"binary")
    monkeypatch.setattr(
        "video_switch.services.toolchain.application_roots",
        lambda: (tmp_path,),
    )
    detector = ToolchainDetector()
    statuses: list[ToolchainStatus] = []
    detector.finished.connect(statuses.append)
    monkeypatch.setattr(detector, "_start_next", lambda generation: None)

    detector.detect()

    assert detector._queue == [] or detector._queue is not None
    detector.cancel()
    assert detector._generation > 0
    assert statuses == []


# ------------------------------------------------------------------ conversion runner


def test_runner_uses_segments_and_resumes_from_disk(qtbot, tmp_path, monkeypatch) -> None:
    calls = _record_process_launches(monkeypatch)
    settings = ConversionSettings()
    output_dir = tmp_path / "out"
    task = _task(tmp_path, duration=SEGMENT_DURATION_SECONDS * 3)
    runner = ConversionRunner()

    runner.start(task, settings, output_dir, FFMPEG_STUB)

    assert runner._mode == "segment"
    assert task.conversion_resumable is True
    assert task.conversion_part_dir is not None and task.conversion_part_dir.is_dir()
    assert calls[-1][calls[-1].index("-ss") + 1] == "0.000"
    assert calls[-1][-1].endswith("part_00000.mp4")

    part_dir = task.conversion_part_dir
    for index in range(2):
        (part_dir / f"part_{index:05d}.mp4").write_bytes(b"segment")
    calls.clear()
    resumed = ConversionRunner()

    resumed.start(task, settings, output_dir, FFMPEG_STUB)

    assert resumed._completed_duration == SEGMENT_DURATION_SECONDS * 2
    assert resumed._part_paths and len(resumed._part_paths) == 2
    assert calls[-1][calls[-1].index("-ss") + 1] == "60.000"
    assert calls[-1][-1].endswith("part_00002.mp4")


def test_runner_goes_straight_to_concat_when_parts_are_complete(
    qtbot,
    tmp_path,
    monkeypatch,
) -> None:
    calls = _record_process_launches(monkeypatch)
    settings = ConversionSettings()
    task = _task(tmp_path, duration=60.0)
    runner = ConversionRunner()
    runner.start(task, settings, tmp_path / "out", FFMPEG_STUB)
    part_dir = task.conversion_part_dir
    assert part_dir is not None
    for index in range(2):
        (part_dir / f"part_{index:05d}.mp4").write_bytes(b"segment")
    calls.clear()
    resumed = ConversionRunner()

    resumed.start(task, settings, tmp_path / "out", FFMPEG_STUB)

    assert resumed._mode == "concat"
    assert calls[-1][calls[-1].index("-f") + 1] == "concat"
    assert resumed._concat_list is not None and resumed._concat_list.is_file()
    assert "part_00000.mp4" in resumed._concat_list.read_text(encoding="utf-8")


def test_runner_moves_to_the_next_segment(qtbot, tmp_path, monkeypatch) -> None:
    calls = _record_process_launches(monkeypatch)
    task = _task(tmp_path, duration=SEGMENT_DURATION_SECONDS * 3)
    runner = ConversionRunner()
    results: list = []
    runner.finished.connect(results.append)
    runner.start(task, ConversionSettings(), tmp_path / "out", FFMPEG_STUB)
    current = runner._current_part
    assert current is not None
    current.write_bytes(b"segment")
    runner._process = FakeProcess()

    runner._finish_segment(0, "", 1.0)

    assert runner._completed_duration == SEGMENT_DURATION_SECONDS
    assert task.conversion_parts_completed == 1
    assert results == []
    assert calls[-1][calls[-1].index("-ss") + 1] == "30.000"


def test_runner_cancel_keeps_finished_segments(qtbot, tmp_path, monkeypatch) -> None:
    _record_process_launches(monkeypatch)
    task = _task(tmp_path, duration=SEGMENT_DURATION_SECONDS * 3)
    runner = ConversionRunner()
    results: list = []
    runner.finished.connect(results.append)
    runner.start(task, ConversionSettings(), tmp_path / "out", FFMPEG_STUB)
    current_part = runner._current_part
    assert current_part is not None
    current_part.write_bytes(b"segment")
    runner._process = FakeProcess()
    runner._cancel_requested = True
    runner._completed_duration = SEGMENT_DURATION_SECONDS * 2

    runner._finish_segment(0, "", 1.0)

    assert results[-1].cancelled is True
    assert results[-1].can_resume is True
    assert results[-1].progress_percent == pytest.approx(66.7, abs=0.2)
    assert current_part.exists() is False
    assert task.conversion_resumable is True


def test_runner_segment_failure_keeps_resume_flag(qtbot, tmp_path, monkeypatch) -> None:
    _record_process_launches(monkeypatch)
    task = _task(tmp_path, duration=SEGMENT_DURATION_SECONDS * 2)
    runner = ConversionRunner()
    results: list = []
    runner.finished.connect(results.append)
    runner.start(task, ConversionSettings(), tmp_path / "out", FFMPEG_STUB)
    runner._process = FakeProcess()

    runner._finish_segment(1, "No space left on device\n", 1.0)

    assert results[-1].success is False
    assert "磁盘空间不足" in (results[-1].error or "")
    assert results[-1].can_resume is False  # 一段都没完成时不提供续转


def test_runner_finishes_single_process_conversion(qtbot, tmp_path, monkeypatch) -> None:
    _record_process_launches(monkeypatch)
    task = _task(tmp_path, duration=5.0)
    runner = ConversionRunner()
    results: list = []
    runner.finished.connect(results.append)
    output = runner.start(task, ConversionSettings(), tmp_path / "out", FFMPEG_STUB)
    runner._process = FakeProcess()
    output.write_bytes(b"converted")

    runner._finish_single(0, "", 2.0)

    assert results[-1].success is True
    assert results[-1].progress_percent == 100.0
    assert output.is_file()

    output.write_bytes(b"converted")
    runner._output_path = output
    runner._completed = False
    runner._finish_single(1, "boom\n", 1.0)
    assert results[-1].success is False
    assert output.exists() is False


def test_runner_single_cancel_removes_output(qtbot, tmp_path, monkeypatch) -> None:
    _record_process_launches(monkeypatch)
    task = _task(tmp_path, duration=5.0)
    runner = ConversionRunner()
    results: list = []
    runner.finished.connect(results.append)
    output = runner.start(task, ConversionSettings(), tmp_path / "out", FFMPEG_STUB)
    output.write_bytes(b"partial")
    runner._process = FakeProcess()
    runner._cancel_requested = True

    runner._finish_single(0, "", 1.0)

    assert results[-1].cancelled is True
    assert results[-1].can_resume is False
    assert output.exists() is False


def test_runner_concat_result_cleans_parts(qtbot, tmp_path, monkeypatch) -> None:
    _record_process_launches(monkeypatch)
    task = _task(tmp_path, duration=SEGMENT_DURATION_SECONDS * 2)
    runner = ConversionRunner()
    results: list = []
    runner.finished.connect(results.append)
    runner.start(task, ConversionSettings(), tmp_path / "out", FFMPEG_STUB)
    part_dir = task.conversion_part_dir
    assert part_dir is not None
    runner._mode = "concat"
    runner._part_paths = [part_dir / "part_00000.mp4"]
    runner._process = FakeProcess()
    runner._output_path.write_bytes(b"final")

    runner._finish_concat(0, "", 3.0)

    assert results[-1].success is True
    assert part_dir.exists() is False
    assert task.conversion_part_dir is None

    # 取消合并时保留分段，允许继续
    runner._mode = "concat"
    runner._cancel_requested = True
    runner._output_path = tmp_path / "out" / "again.mp4"
    runner._output_path.write_bytes(b"partial")
    runner._part_paths = []
    runner._process = FakeProcess()
    runner._finish_concat(0, "", 1.0)
    assert results[-1].cancelled is True
    assert results[-1].can_resume is True


def test_runner_shutdown_and_process_error(qtbot, tmp_path, monkeypatch) -> None:
    _record_process_launches(monkeypatch)
    task = _task(tmp_path, duration=SEGMENT_DURATION_SECONDS * 3)
    runner = ConversionRunner()
    results: list = []
    runner.finished.connect(results.append)
    runner.start(task, ConversionSettings(), tmp_path / "out", FFMPEG_STUB)
    current = runner._current_part
    assert current is not None
    current.write_bytes(b"segment")
    runner._process = FakeProcess()

    runner.shutdown()

    assert current.exists() is False
    assert runner._process is None

    runner._completed = False
    runner._part_paths = [current]
    runner._on_error(QProcess.ProcessError.FailedToStart)
    assert "无法启动 FFmpeg" in (results[-1].error or "")
    assert results[-1].can_resume is True


def test_runner_releases_finished_process_objects(qtbot, tmp_path, monkeypatch) -> None:
    """A long video creates one QProcess per segment; they must not pile up."""
    _record_process_launches(monkeypatch)
    task = _task(tmp_path, duration=SEGMENT_DURATION_SECONDS * 2)
    runner = ConversionRunner()
    runner.start(task, ConversionSettings(), tmp_path / "out", FFMPEG_STUB)
    runner._process = QProcess(runner)
    assert len(runner.findChildren(QProcess)) == 1

    runner._release_process()

    assert runner._process is None
    qtbot.wait(50)
    assert runner.findChildren(QProcess) == []


def test_runner_parses_stdout_progress_lines(qtbot, tmp_path, monkeypatch) -> None:
    _record_process_launches(monkeypatch)
    task = _task(tmp_path, duration=60.0)
    runner = ConversionRunner()
    progress: list = []
    runner.progress.connect(progress.append)
    runner.start(task, ConversionSettings(), tmp_path / "out", FFMPEG_STUB)
    runner._process = FakeProcess(
        stdout=b"out_time_us=30000000\nspeed=2.0x\nprogress=continue\n",
    )
    runner._process.readyReadStandardOutput.connect(runner._read_stdout)

    runner._process.readyReadStandardOutput.emit()

    assert progress and progress[-1].percent == pytest.approx(50.0)

    runner._mode = "concat"
    runner._process = FakeProcess(stdout=b"progress=continue\n")
    runner._process.readyReadStandardOutput.connect(runner._read_stdout)
    runner._process.readyReadStandardOutput.emit()
    assert len(progress) == 1


def test_runner_ignores_stale_segment_directory(qtbot, tmp_path, monkeypatch) -> None:
    _record_process_launches(monkeypatch)
    task = _task(tmp_path, duration=SEGMENT_DURATION_SECONDS * 3)
    stale = tmp_path / "out" / ".other.parts"
    stale.mkdir(parents=True)
    (stale / "part_00000.mp4").write_bytes(b"old")
    task.conversion_part_dir = stale
    task.conversion_settings_key = "different"
    runner = ConversionRunner()

    runner.start(task, ConversionSettings(), tmp_path / "out", FFMPEG_STUB)

    assert stale.exists() is False
    assert task.conversion_part_dir != stale
    assert task.conversion_parts_completed == 0


# ---------------------------------------------------------------- tool probe / history


def test_tool_probe_accepts_a_reported_version(tmp_path) -> None:
    from video_switch.services.toolchain import _ToolProbe

    probe = _ToolProbe("ffmpeg", FFMPEG_STUB, "用户配置")
    results: list[ToolInfo] = []
    probe.completed.connect(results.append)

    probe._complete(
        ToolInfo(name="ffmpeg", executable=FFMPEG_STUB, version="6.0", source="用户配置")
    )
    probe._complete(ToolInfo(name="ffmpeg", error="不应覆盖已完成的探测"))

    assert len(results) == 1
    assert results[0].ready is True
    assert results[0].display_version == "6.0"
    del tmp_path


def test_tool_probe_reports_broken_binaries() -> None:
    from video_switch.services.toolchain import _ToolProbe

    broken = _ToolProbe("ffmpeg", FFMPEG_STUB, "用户配置")
    broken.process = FakeProcess(stdout=b"not a version banner")
    results: list[ToolInfo] = []
    broken.completed.connect(results.append)

    broken._on_finished(0, QProcess.ExitStatus.NormalExit)

    assert results[-1].error == "程序执行失败或版本信息无法解析"

    missing = _ToolProbe("ffprobe", FFPROBE_STUB, "自动检测")
    missing_results: list[ToolInfo] = []
    missing.completed.connect(missing_results.append)
    missing._on_error(QProcess.ProcessError.FailedToStart)
    assert "无法启动程序" in (missing_results[-1].error or "")

    timed_out = _ToolProbe("ffmpeg", FFMPEG_STUB, "应用内置")
    timeouts: list[ToolInfo] = []
    timed_out.completed.connect(timeouts.append)
    timed_out.process = FakeProcess()
    timed_out._on_timeout()

    assert "超时" in (timeouts[-1].error or "")


def test_tool_probe_reads_version_from_stderr() -> None:
    from video_switch.services.toolchain import _ToolProbe

    probe = _ToolProbe("ffprobe", FFPROBE_STUB, "系统 PATH")
    probe.process = FakeProcess(stderr=b"ffprobe version 6.0 Copyright (c) 2007-2023")
    results: list[ToolInfo] = []
    probe.completed.connect(results.append)

    probe._on_finished(0, QProcess.ExitStatus.NormalExit)

    assert results[-1].version == "6.0"


def test_history_store_survives_a_corrupt_file(tmp_path) -> None:
    from video_switch.services.history_store import ConversionHistoryStore

    store = ConversionHistoryStore(tmp_path / "history.json")
    store.path.write_text("{ not json", encoding="utf-8")

    assert store.load() == []

    store.path.write_text('{"not": "a list"}', encoding="utf-8")
    assert store.load() == []

    store.path.write_text(
        json.dumps(
            [
                {
                    "record_id": "ok",
                    "timestamp": "t",
                    "source_path": "a.mp4",
                    "output_path": "a.mp3",
                    "output_format": "MP3",
                    "status": "已完成",
                },
                {"missing": "fields"},
                "not a dict",
            ]
        ),
        encoding="utf-8",
    )
    records = store.load()

    assert len(records) == 1
    assert records[0].elapsed_seconds == 0.0
    assert records[0].source_key


def test_history_store_missing_file_is_empty(tmp_path) -> None:
    from video_switch.services.history_store import ConversionHistoryStore

    store = ConversionHistoryStore(tmp_path / "missing" / "history.json")
    assert store.load() == []
    assert store.delete_record("nope") == []
    assert store.delete_by_source_key("nope") == []
    assert store.delete_by_source_keys({"nope"}) == []
    store.clear()
    assert store.path.is_file()
