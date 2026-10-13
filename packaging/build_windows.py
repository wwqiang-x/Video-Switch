"""Build the Windows distribution: frozen app + bundled FFmpeg + zip archive."""

import shutil
import subprocess
import sys
import time
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGING = ROOT / "packaging"
DIST = ROOT / "dist"
APP_DIR = DIST / "VideoSwitch"
FFMPEG_SOURCE = ROOT / ".tools" / "ffmpeg" / "bin"


def report(*args) -> None:
    print(*args, flush=True)


def project_version() -> str:
    with (ROOT / "pyproject.toml").open("rb") as handle:
        return str(tomllib.load(handle)["project"]["version"])


def run(command: list[str]) -> None:
    report("$ " + " ".join(command))
    subprocess.run(command, check=True, cwd=ROOT)


def ensure_icon() -> None:
    icon = PACKAGING / "VideoSwitch.ico"
    if icon.is_file():
        return
    run([sys.executable, str(PACKAGING / "make_icon.py")])


def build_with_pyinstaller() -> None:
    if APP_DIR.exists():
        shutil.rmtree(APP_DIR)
    run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            str(PACKAGING / "VideoSwitch.spec"),
            "--noconfirm",
            "--clean",
            "--distpath",
            str(DIST),
            "--workpath",
            str(ROOT / "build"),
        ]
    )


def bundle_ffmpeg() -> None:
    if not FFMPEG_SOURCE.is_dir():
        raise SystemExit(
            f"未找到 FFmpeg：{FFMPEG_SOURCE}\n请把 ffmpeg 与 ffprobe 放到该目录后重新打包。",
        )
    target = APP_DIR / "ffmpeg" / "bin"
    target.mkdir(parents=True, exist_ok=True)
    for name in ("ffmpeg.exe", "ffprobe.exe"):
        shutil.copy2(FFMPEG_SOURCE / name, target / name)
    (APP_DIR / "ffmpeg" / "BUNDLED_FFMPEG.txt").write_text(
        "本目录下的 ffmpeg.exe 与 ffprobe.exe 为 FFmpeg 6.0-essentials_build\n"
        "（来源：https://www.gyan.dev/ffmpeg/builds/），启用 GPL 组件，\n"
        "以 GNU General Public License version 3 分发。\n"
        "完整许可证：https://www.gnu.org/licenses/gpl-3.0.html\n",
        encoding="utf-8",
    )


def copy_documents() -> None:
    for name in ("LICENSE", "THIRD_PARTY_NOTICES.md"):
        shutil.copy2(ROOT / name, APP_DIR / name)


def make_archive(version: str) -> Path:
    archive = DIST / f"VideoSwitch-{version}-win64.zip"
    archive.unlink(missing_ok=True)
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as bundle:
        for path in sorted(APP_DIR.rglob("*")):
            if path.is_file():
                bundle.write(path, path.relative_to(DIST))
    return archive


def folder_size(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def main() -> int:
    version = project_version()
    report(f"== 打包 Video Switch {version}")
    started = time.monotonic()
    ensure_icon()
    build_with_pyinstaller()
    bundle_ffmpeg()
    copy_documents()
    archive = make_archive(version)
    report("")
    report(f"分发目录：{APP_DIR}（{folder_size(APP_DIR) / 1024 / 1024:.0f} MB）")
    report(f"压缩包　：{archive}（{archive.stat().st_size / 1024 / 1024:.0f} MB）")
    report(f"耗时　　：{time.monotonic() - started:.1f} 秒")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
