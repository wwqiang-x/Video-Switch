"""Advanced conversion parameter explanations."""

from PySide6.QtWidgets import QWidget

from video_switch.ui.help_dialog import HelpCard, HelpCardDialog

ADVANCED_GUIDES = (
    HelpCard(
        code="VC",
        title="视频编码",
        summary="决定视频画面的压缩方式和播放兼容性。",
        use_case="优先兼容选 H.264；希望文件更小可选 H.265 或 AV1。",
        note="H.265、AV1 通常编码更慢，旧设备或旧软件可能无法播放。",
        action_label="建议",
    ),
    HelpCard(
        code="CRF",
        title="画质等级",
        summary="控制画质与文件体积的平衡，数值越低画质越高、文件越大。",
        use_case="18 偏高质量，23 适合日常使用，28 适合更小体积。",
        note="通常使用 18 到 28；过低会明显增大文件，过高会损失细节。",
        action_label="建议",
    ),
    HelpCard(
        code="AC",
        title="音频编码",
        summary="决定声音的压缩格式和设备兼容性。",
        use_case="MP4/MKV 优先 AAC；WebM 优先 Opus；WAV 使用 PCM。",
        note="更换音频编码可能影响播放器兼容性和音质。",
        action_label="建议",
    ),
    HelpCard(
        code="AB",
        title="音频码率",
        summary="控制音频每秒占用的数据量。",
        use_case="128k 适合语音，192k 适合日常视频，256k 或 320k 适合音乐。",
        note="码率越高，声音细节越丰富，但文件也会更大。",
        action_label="建议",
    ),
    HelpCard(
        code="AUD",
        title="保留音频",
        summary="决定输出文件中是否保留声音轨道。",
        use_case="需要声音时保持勾选；只制作无声视频时可以取消。",
        note="MP3、WAV 等纯音频格式会强制保留音频，GIF 会自动取消音频。",
        action_label="建议",
    ),
)


class AdvancedHelpDialog(HelpCardDialog):
    """Modal guide that explains advanced conversion parameters."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(
            window_title="高级参数说明",
            heading="理解高级转换参数",
            description=(
                "高级参数会影响画质、文件大小、编码速度和设备兼容性。如果不确定，优先使用默认值。"
            ),
            cards=ADVANCED_GUIDES,
            parent=parent,
        )
