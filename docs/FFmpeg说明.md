# FFmpeg 入门说明

## 它是什么

FFmpeg 是一套开源的音视频命令行工具。本项目将它作为本地处理引擎使用，
不研究源码，也不调用 FFmpeg C API。

## 项目会使用哪些工具

| 工具 | 作用 |
| --- | --- |
| `ffmpeg` | 截取缩略图、转换视频、提取音频 |
| `ffprobe` | 读取时长、分辨率、编码和码率等信息 |
| `ffplay` | 播放媒体，本项目不使用 |

## 应用中的处理流程

1. 启动时查找并验证 ffmpeg 和 ffprobe。
2. 用户导入视频。
3. 应用启动 `ffprobe` 并读取 JSON 格式信息。
4. 应用启动 `ffmpeg` 截取一帧作为缩略图。
5. 用户选择转换预设。
6. 应用启动 `ffmpeg` 执行转换并解析进度。
7. 用户取消任务时，应用终止对应的 ffmpeg 进程。

## 开发阶段工具位置

当前开发环境使用 FFmpeg 6.0，程序位于 `.tools/ffmpeg/bin`。该目录已被 Git
忽略，只用于本地测试。应用支持自动检测该目录，也支持用户在设置窗口中手动
选择 `ffmpeg.exe` 和 `ffprobe.exe`。

## 视频信息读取

应用使用 ffprobe 的 JSON 输出读取媒体信息：

```powershell
ffprobe -v error -print_format json -show_format -show_streams input.mp4
```

应用会解析视频流和音频流，提取时长、分辨率、帧率、编码、码率、采样率和
声道数。读取失败时不会终止其他任务。

## 缩略图生成

应用使用 ffmpeg 从指定时间点截取一帧，并缩放到适合预览的宽度：

```powershell
ffmpeg -ss 10 -i input.mp4 -frames:v 1 -vf "scale='min(1920,iw)':-2" -q:v 1 thumbnail.jpg
```

如果首个位置截取失败，应用会依次尝试第 1 秒、视频中段、结尾和首帧。
缩略图固定从视频约 10% 位置开始尝试，不是随机抽取。生成的图片保存在应用
缓存目录，不修改源视频。1080p 视频会生成完整 1920×1080 缩略图，720p
视频保持 1280×720，不进行无意义的放大。

## 转换命令预览

步骤 6 会根据用户选择生成 FFmpeg 参数，但不会执行。例如 MP4 默认配置大致为：

```powershell
ffmpeg -y -i input.mp4 -c:v libx264 -preset medium -crf 23 -c:a aac -b:a 192k -movflags +faststart output.mp4
```

WebM、MP3、WAV 和 GIF 会使用各自对应的编码参数和输出扩展名。

## 转换进度

实际执行转换时，应用会追加以下参数：

```powershell
-progress pipe:1 -nostats
```

FFmpeg 会把 `out_time_us`、`speed` 和 `progress` 等键值持续写入标准输出。
应用根据媒体时长换算百分比和剩余时间；取消时终止对应进程并清理未完成文件。

## 面试需要掌握的概念

- MP4、MKV、WebM 是容器格式。
- H.264、VP9、AAC 是编码格式。
- 分辨率、帧率、码率和 CRF 影响画质和文件大小。
- ffprobe 用来读信息，ffmpeg 用来处理和输出。
- 本项目使用命令行进程，不接入 FFmpeg API。

具体命令会在对应开发步骤中补充，并说明每个参数的作用。
