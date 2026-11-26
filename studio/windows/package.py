"""Assemble the portable Windows x64 release from verified upstream ZIP archives."""

import argparse
import hashlib
import shutil
from pathlib import Path
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[2]
PYTHON_SHA256 = "9e35319bffedab8b36ad44d8f377cb4f1733bcec257a0b6d04d94f01486ddb38"
FFMPEG_SHA256 = "b9bbbb3acece000cbeec994f856649354e52c773807841e78908374b24d658fd"


def verify(path, expected):
    with path.open("rb") as file:
        if hashlib.file_digest(file, "sha256").hexdigest() != expected:
            raise ValueError(f"Unexpected SHA-256 for {path}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("python_zip", type=Path)
    parser.add_argument("ffmpeg_zip", type=Path)
    parser.add_argument("launcher_exe", type=Path)
    parser.add_argument("--destination", type=Path, default=ROOT / "MovieClip-Windows")
    args = parser.parse_args()
    verify(args.python_zip, PYTHON_SHA256)
    verify(args.ffmpeg_zip, FFMPEG_SHA256)

    destination = args.destination
    destination.mkdir()
    python = destination / "runtime" / "python"
    with ZipFile(args.python_zip) as archive:
        archive.extractall(python)
    with (python / "python313._pth").open("ab") as paths:
        paths.write(b"\r\n..\\app\r\n")

    ffmpeg = destination / "runtime" / "ffmpeg"
    ffmpeg.mkdir()
    with ZipFile(args.ffmpeg_zip) as archive:
        for member in ("bin/ffmpeg.exe", "bin/ffprobe.exe", "LICENSE", "README.txt"):
            entry = next(name for name in archive.namelist() if name.endswith("/" + member))
            with archive.open(entry) as source, (ffmpeg / Path(member).name).open("wb") as output:
                shutil.copyfileobj(source, output)

    app = destination / "runtime" / "app"
    (app / "studio").mkdir(parents=True)
    shutil.copy2(ROOT / "movieclip_studio.py", app)
    shutil.copy2(ROOT / "studio" / "engine.py", app / "studio")
    shutil.copytree(ROOT / "studio" / "web", app / "studio" / "web")
    shutil.copy2(args.launcher_exe, destination / "MovieClip.exe")
    shutil.copy2(Path(__file__).with_name("사용법.txt"), destination)


if __name__ == "__main__":
    main()
