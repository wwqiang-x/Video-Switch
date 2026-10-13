# 第三方组件声明

## FFmpeg / ffprobe

`VideoSwitch-<版本>-win64.zip` 内置以下可执行文件，随应用一起分发：

| 文件 | 版本 | 来源 |
| --- | --- | --- |
| `ffmpeg/bin/ffmpeg.exe` | 6.0-essentials_build | [gyan.dev Windows builds](https://www.gyan.dev/ffmpeg/builds/) |
| `ffmpeg/bin/ffprobe.exe` | 6.0-essentials_build | [gyan.dev Windows builds](https://www.gyan.dev/ffmpeg/builds/) |

上述构建启用了 GPL 组件（x264、x265、libvpx 等），以 **GNU General Public License
version 3** 分发。它们以**独立可执行文件**的形式随应用分发，应用与 FFmpeg 之间通过
命令行进程调用交互，未进行静态或动态链接，因此本项目的源代码仍以 MIT 许可证发布。

- FFmpeg 项目主页：<https://ffmpeg.org/>
- FFmpeg 源代码：<https://ffmpeg.org/download.html>
- GPL v3 全文：<https://www.gnu.org/licenses/gpl-3.0.html>
- 压缩包内 `ffmpeg/BUNDLED_FFMPEG.txt` 记录了随包分发的版本与来源

## PySide6 / Qt

界面基于 PySide6（Qt for Python），以 **LGPL v3** 分发。

- 项目主页：<https://doc.qt.io/qtforpython/>
- 许可证：<https://www.gnu.org/licenses/lgpl-3.0.html>
