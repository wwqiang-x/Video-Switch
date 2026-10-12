"""Output format guide shown from the conversion settings panel."""

from PySide6.QtWidgets import QWidget

from video_switch.ui.help_dialog import HelpCard, HelpCardDialog

FormatGuide = HelpCard

FORMAT_GUIDES = (
    FormatGuide(
        code="MP4",
        title="通用视频",
        summary="兼容性最好，适合在手机、平板、网页和常见播放器中播放。",
        use_case="发送视频、上传平台、日常保存。",
        note="默认使用 H.264 + AAC，兼顾画质、体积和兼容性。",
    ),
    FormatGuide(
        code="MKV",
        title="多轨视频容器",
        summary="可以封装多条音频、字幕和不同编码的视频流。",
        use_case="本地收藏、影视资源、需要字幕或多音轨的视频。",
        note="兼容性不如 MP4，部分手机和网页播放器支持有限。",
    ),
    FormatGuide(
        code="WebM",
        title="网页视频",
        summary="面向网页播放，通常使用 VP9 或 AV1 视频编码。",
        use_case="网页项目、在线演示、浏览器内播放。",
        note="编码速度可能较慢，部分旧软件不能直接打开。",
    ),
    FormatGuide(
        code="MP3",
        title="通用音频",
        summary="只保留音频，兼容性很高，文件体积较小。",
        use_case="音乐、播客、语音和只需要声音的场景。",
        note="会丢失视频画面，并且属于有损压缩。",
    ),
    FormatGuide(
        code="WAV",
        title="无损音频",
        summary="使用 PCM 音频，音质损失最少，但文件体积明显更大。",
        use_case="音频编辑、后期制作和需要保留原始音质的场景。",
        note="不支持视频画面，不适合直接用于网络传输。",
    ),
    FormatGuide(
        code="GIF",
        title="循环动画",
        summary="生成自动循环播放的动画图片，不包含声音。",
        use_case="聊天表情、简短演示和无声循环动画。",
        note="颜色数量有限，文件可能较大，不适合长视频。",
    ),
)


class FormatHelpDialog(HelpCardDialog):
    """Modal guide that explains all supported output formats."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(
            window_title="输出格式说明",
            heading="选择适合的输出格式",
            description=(
                "不同格式适用于不同场景。兼容性、文件大小、编码速度和音视频能力各有取舍。"
            ),
            cards=FORMAT_GUIDES,
            parent=parent,
        )
