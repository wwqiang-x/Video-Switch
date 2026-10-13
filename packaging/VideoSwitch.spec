# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 配置：单文件夹分发，内置 FFmpeg。

用法（由 packaging/build_windows.py 调用）：
    uv run pyinstaller packaging/VideoSwitch.spec --noconfirm --clean
"""

import os
from pathlib import Path

ROOT = Path(SPECPATH).resolve().parent
# 打包排查用：设置 VIDEOSWITCH_BUILD_CONSOLE=1 会构建带控制台的版本，
# 未捕获异常与导入错误会直接打印到终端，便于定位。
CONSOLE = os.environ.get("VIDEOSWITCH_BUILD_CONSOLE") == "1"

a = Analysis(
    [str(ROOT / "src" / "video_switch" / "__main__.py")],
    pathex=[str(ROOT / "src")],
    binaries=[],
    # 界面 SVG 属于数据文件，PyInstaller 不会自动收集，必须显式声明。
    datas=[(str(ROOT / "src" / "video_switch" / "resources"), "video_switch/resources")],
    hiddenimports=["PySide6.QtSvg"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # 未使用的大型 Qt 模块与标准库，排除以缩小体积。
    excludes=[
        "PySide6.QtQml",
        "PySide6.QtQuick",
        "PySide6.QtQuickWidgets",
        "PySide6.QtNetwork",
        "PySide6.QtSql",
        "PySide6.QtTest",
        "PySide6.QtPdf",
        "PySide6.QtCharts",
        "PySide6.QtOpenGL",
        "PySide6.QtOpenGLWidgets",
        "PySide6.Qt3DCore",
        "PySide6.QtMultimedia",
        "PySide6.QtWebSockets",
        "tkinter",
        "unittest",
        "pytest",
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

# 这些库由 Windows 自己提供，PyInstaller 有时会从 Python 发行目录里收集到
# 版本不同的副本并打进包内，反而把系统版本遮住：
#   - api-ms-win-*：API 集转发库，打进包内会让 Qt 找不到新系统才有的符号；
#   - icuuc/icudt/icu：Qt 通过系统 ICU 解析，打包第三方版本会导致符号缺失；
#   - ucrtbase：通用 C 运行时，Windows 10 及以上自带。
OS_PROVIDED = ("api-ms-win-", "ucrtbase.dll", "icuuc.dll", "icudt", "icu.dll")


def _keep(entry) -> bool:
    name = Path(entry[0]).name.lower()
    return not name.startswith(OS_PROVIDED)


a.binaries = [entry for entry in a.binaries if _keep(entry)]

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="VideoSwitch",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=CONSOLE,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=[str(ROOT / "packaging" / "VideoSwitch.ico")],
    version=str(ROOT / "packaging" / "version_info.txt"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="VideoSwitch",
)
