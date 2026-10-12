"""Turn raw FFmpeg and ffprobe failures into messages a normal user can act on."""

from __future__ import annotations

SOURCE_MISSING = "源文件已被移动或删除，请重新导入后再转换"
FALLBACK_CONVERSION = "转换失败，请展开“转换日志”查看 FFmpeg 的详细输出"
FALLBACK_PROBE = "无法读取该文件，可能不是有效的视频，或文件已经损坏"

# Ordered: the first matching rule wins, so put specific causes before generic ones.
_CONVERSION_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (
        (
            "no space left on device",
            "disk full",
            "error writing trailer",
            "cannot write trailer",
            "error writing header",
        ),
        "磁盘空间不足，请清理磁盘或更换输出目录后重试",
    ),
    (
        (
            "permission denied",
            "access is denied",
            "read-only file system",
            "error opening output file",
            "unable to open output file",
        ),
        "无法写入输出目录，请检查目录权限，或确认该目录没有被删除",
    ),
    (
        (
            "no such file or directory",
            "could not open input",
            "cannot open",
            "error opening input",
        ),
        SOURCE_MISSING,
    ),
    (
        (
            "invalid data found",
            "moov atom not found",
            "could not find codec parameters",
            "error while decoding",
            "invalid nal size",
        ),
        "视频内容无法解析，文件可能已损坏或格式不受支持",
    ),
    (
        ("unknown encoder", "encoder not found", "unknown codec", "unknown decoder"),
        "当前 FFmpeg 不包含所选编码器，请在高级设置里更换编码",
    ),
    (
        (
            "file is being used by another process",
            "being used by another process",
            "device or resource busy",
            "text file busy",
        ),
        "输出文件正被其他程序占用，请关闭相关程序后重试",
    ),
    (
        (
            "not supported",
            "unsupported",
            "invalid argument",
            "error initializing output stream",
            "specified pixel format",
            "error while opening encoder",
            "conversion failed",
        ),
        "当前参数组合不被该编码器支持，请调整编码、分辨率或帧率后重试",
    ),
)

_PROBE_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("permission denied", "access is denied"), "没有权限读取该文件，请检查文件属性"),
    (("no such file or directory",), "文件不存在或无法访问，可能已被移动"),
    (
        ("invalid data found", "moov atom not found", "could not find codec parameters"),
        FALLBACK_PROBE,
    ),
    (("timed out", "timeout"), "读取视频信息超时，请确认文件可以正常播放"),
)

_MAX_DETAIL = 160


def last_meaningful_line(text: str) -> str:
    """Return the last non-empty line of a command log, trimmed for display."""
    for line in reversed((text or "").splitlines()):
        stripped = line.strip()
        if stripped:
            return stripped[:_MAX_DETAIL]
    return ""


def describe_conversion_error(log: str, fallback: str = "") -> str:
    """Classify one failed conversion and explain it in plain language."""
    text = (log or "").lower()
    for needles, message in _CONVERSION_RULES:
        if any(needle in text for needle in needles):
            return message
    detail = last_meaningful_line(log) or fallback
    if detail and detail != FALLBACK_CONVERSION:
        return f"{FALLBACK_CONVERSION}（最后一行：{detail}）"
    return FALLBACK_CONVERSION


def describe_probe_error(text: str) -> str:
    """Classify one failed ffprobe run and explain it in plain language."""
    lowered = (text or "").lower()
    for needles, message in _PROBE_RULES:
        if any(needle in lowered for needle in needles):
            return message
    return FALLBACK_PROBE
