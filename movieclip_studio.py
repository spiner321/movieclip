#!/usr/bin/env python3
import argparse
import contextlib
import hmac
import json
import mimetypes
import os
import re
import secrets
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlsplit

from studio.engine import StudioError, frame, local_path, probe, publish, render, render_plan, seconds


ROOT = Path(__file__).resolve().parent
WEB = ROOT / "studio" / "web"
ASSETS = {
    "/studio.css": ("studio.css", "text/css; charset=utf-8"),
    "/studio.js": ("studio.js", "text/javascript; charset=utf-8"),
    "/icon.svg": ("icon.svg", "image/svg+xml"),
}
MEDIA_TYPES = {".mkv": "video/x-matroska", ".mov": "video/quicktime", ".m4v": "video/mp4"}
CHUNK = 1024 * 1024


def settings_path():
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
        return base / "MovieClip Studio" / "settings.json"
    base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "movieclip-studio" / "settings.json"


class Workspace:
    def __init__(self, input_dir, output_dir, settings_file):
        self.input_dir = input_dir
        self.settings_file = settings_file
        self.default_output_dir = output_dir
        self.last_output_dir = None
        with contextlib.suppress(OSError, ValueError, AttributeError, StudioError):
            saved = json.loads(settings_file.read_text(encoding="utf-8"))
            self.default_output_dir = local_path(saved.get("output_dir"), directory=True)
        self.folder_picker = os.environ.get("MOVIECLIP_LAUNCHER") if os.name == "nt" else None
        self.file_picker = self.folder_picker if os.environ.get("MOVIECLIP_OPEN_DIALOG") == "1" else None
        self.token = secrets.token_urlsafe(32)
        self.ready = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))
        self.lock = threading.RLock()
        self.clips = {}
        self.clip_readers = {}
        self.removed_clips = {}
        self.job = None
        self.process = None
        self.worker = None
        self.cancelled = False
        self.outputs = {}

    def require_engine(self):
        if not self.ready:
            raise StudioError("FFmpeg와 FFprobe를 WSL에 설치한 뒤 편집기를 다시 열어 주세요.")

    def import_clip(self, name, source=None, stream=None, length=0):
        self.require_engine()
        clip_id = uuid.uuid4().hex
        folder = self.input_dir / clip_id
        folder.mkdir()
        try:
            if stream is not None:
                if length > shutil.disk_usage(folder).free:
                    raise StudioError("임시 저장 공간이 부족합니다. 경로로 영상 열기를 사용해 주세요.")
                extension = Path(name).suffix
                if not re.fullmatch(r"\.[A-Za-z0-9]{1,12}", extension):
                    extension = ".video"
                source = folder / ("source" + extension)
                with source.open("wb") as file:
                    remaining = length
                    while remaining:
                        chunk = stream.read(min(CHUNK, remaining))
                        if not chunk:
                            raise StudioError("영상 가져오기가 중단되었습니다.")
                        file.write(chunk)
                        remaining -= len(chunk)
            clip = probe(clip_id, source, name, folder)
            with contextlib.suppress(subprocess.SubprocessError, OSError):
                thumbnail = frame(clip, min(2, clip.duration * 0.12), 256)
                if thumbnail:
                    (folder / "thumbnail.jpg").write_bytes(thumbnail)
            with self.lock:
                self.clips[clip_id] = clip
            return clip.describe()
        except Exception:
            shutil.rmtree(folder, ignore_errors=True)
            raise

    def remove(self, clip_id):
        with self.lock:
            clip = self.clips.pop(clip_id, None)
            if clip:
                self.removed_clips[clip_id] = clip.workspace
        self.clean_removed_clips()

    @contextlib.contextmanager
    def use_clip(self, clip_id):
        with self.lock:
            clip = self.clips.get(clip_id)
            if clip:
                self.clip_readers[clip_id] = self.clip_readers.get(clip_id, 0) + 1
        try:
            yield clip
        finally:
            if clip:
                with self.lock:
                    self.clip_readers[clip_id] -= 1
                    if not self.clip_readers[clip_id]:
                        del self.clip_readers[clip_id]
                self.clean_removed_clips()

    def clean_removed_clips(self):
        with self.lock:
            active = self.job["clips"] if self.job and self.job["status"] == "running" else ()
            released = [key for key in self.removed_clips if key not in self.clip_readers and key not in active]
            folders = [self.removed_clips.pop(key) for key in released]
        for folder in folders:
            shutil.rmtree(folder, ignore_errors=True)

    def set_default_output(self, value):
        output_dir = local_path(value, directory=True)
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryFile(dir=output_dir):
                pass
        except OSError as error:
            raise StudioError("선택한 폴더에 저장할 수 없습니다. 폴더 경로와 쓰기 권한을 확인해 주세요.") from error
        with self.lock:
            draft = None
            try:
                self.settings_file.parent.mkdir(parents=True, exist_ok=True)
                with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.settings_file.parent,
                                                 delete=False) as file:
                    draft = Path(file.name)
                    json.dump({"output_dir": str(output_dir)}, file, ensure_ascii=False)
                draft.replace(self.settings_file)
            except OSError as error:
                raise StudioError("기본 폴더 설정을 저장할 수 없습니다. 설정 폴더의 쓰기 권한을 확인해 주세요.") from error
            finally:
                if draft:
                    with contextlib.suppress(OSError):
                        draft.unlink(missing_ok=True)
            self.default_output_dir = output_dir
        return str(output_dir)

    def state(self):
        with self.lock:
            return {"ready": self.ready, "clips": [clip.describe() for clip in self.clips.values()],
                    "job": self.job_status(), "output_dir": str(self.last_output_dir or self.default_output_dir),
                    "default_output_dir": str(self.default_output_dir),
                    "folder_picker": bool(self.folder_picker), "file_picker": bool(self.file_picker)}

    def job_status(self):
        with self.lock:
            return self.job.copy() if self.job else None

    def start_job(self, options):
        self.require_engine()
        with self.lock:
            if self.job and self.job["status"] == "running":
                raise StudioError("진행 중인 내보내기가 있습니다.")
            ids = options.get("clips")
            if not isinstance(ids, list) or any(not isinstance(key, str) or key not in self.clips for key in ids):
                raise StudioError("목록에 있는 영상을 선택해 주세요.")
            if len(set(ids)) != len(ids):
                raise StudioError("동일한 영상을 한 번만 선택해 주세요.")
            clips = [self.clips[key] for key in ids]
            output_dir = local_path(options.get("output_dir", str(self.default_output_dir)), directory=True)
            try:
                output_dir.mkdir(parents=True, exist_ok=True)
                staging = tempfile.TemporaryDirectory(prefix=".render-", dir=output_dir)
            except OSError as error:
                raise StudioError("선택한 폴더에 저장할 수 없습니다. 폴더 경로와 쓰기 권한을 확인해 주세요.") from error
            try:
                plan = render_plan(options, clips, Path(staging.name))
            except Exception:
                staging.cleanup()
                raise
            self.cancelled = False
            self.job = {"id": uuid.uuid4().hex, "status": "running", "progress": 0,
                        "mode": options["mode"], "clips": ids, "files": [], "output_dir": str(output_dir)}
            self.worker = threading.Thread(target=self.run_job, args=(staging, plan, output_dir), daemon=True)
            self.worker.start()
            return self.job_status()

    def run_job(self, staging, plan, output_dir):
        try:
            with staging:
                total = sum(duration for _, _, duration in plan)
                completed = 0

                def update(fraction):
                    with self.lock:
                        self.job["progress"] = min(99, round(100 * (completed + duration * fraction) / total))

                for args, _, duration in plan:
                    with self.lock:
                        if self.cancelled:
                            raise StudioError("내보내기를 취소했습니다.")
                    render(args, duration, update, self.manage_process)
                    completed += duration
                with self.lock:
                    if self.cancelled:
                        raise StudioError("내보내기를 취소했습니다.")
                    paths = publish([path for _, path, _ in plan], output_dir)
                    files = []
                    for path in paths:
                        key = uuid.uuid4().hex
                        self.outputs[key] = path
                        files.append({"name": path.name, "url": f"/output/{key}"})
                    self.last_output_dir = output_dir
                    self.job.update(status="done", progress=100, files=files)
        except (StudioError, OSError, subprocess.SubprocessError) as error:
            with self.lock:
                self.job.update(status="cancelled" if self.cancelled else "failed",
                                error="내보내기를 취소했습니다." if self.cancelled else str(error))
        finally:
            with self.lock:
                if self.worker is threading.current_thread():
                    self.process = None
            self.clean_removed_clips()

    def manage_process(self, process):
        with self.lock:
            self.process = process
            if self.cancelled and process:
                with contextlib.suppress(ProcessLookupError):
                    process.terminate()

    def cancel_job(self, job_id):
        with self.lock:
            if self.job and self.job["id"] == job_id and self.job["status"] == "running":
                self.cancelled = True
                if self.process:
                    with contextlib.suppress(ProcessLookupError):
                        self.process.terminate()


class StudioHandler(BaseHTTPRequestHandler):
    server_version = "MovieClip"
    sys_version = ""

    def log_message(self, format, *args):
        if self.server.verbose:
            super().log_message(format, *args)

    @property
    def app(self):
        return self.server.app

    def do_GET(self):
        self.handle_request()

    def do_HEAD(self):
        self.handle_request()

    def do_POST(self):
        self.handle_request()

    def handle_request(self):
        port = self.server.server_port
        if self.headers.get("Host") not in (f"localhost:{port}", f"127.0.0.1:{port}"):
            self.send_json({"error": "로컬 주소로 접속해 주세요."}, 403)
            return
        url = urlsplit(self.path)
        try:
            if self.command == "POST":
                token = self.headers.get("X-Studio-Token", "")
                if not hmac.compare_digest(token.encode("utf-8"), self.app.token.encode("ascii")):
                    self.send_json({"error": "편집기 화면을 새로 고쳐 주세요."}, 403)
                    return
                self.post(url.path)
            else:
                self.get(url)
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            return
        except StudioError as error:
            self.send_json({"error": str(error)}, 400)
        except (subprocess.SubprocessError, OSError) as error:
            self.log_error("%s", error)
            self.send_json({"error": "파일을 읽거나 저장할 수 없습니다. 접근 권한과 저장 공간을 확인해 주세요."}, 400)

    def get(self, url):
        path = url.path
        if path == "/":
            html = (WEB / "index.html").read_text(encoding="utf-8")
            self.send_bytes(html.replace("__STUDIO_TOKEN__", self.app.token).encode("utf-8"),
                            "text/html; charset=utf-8")
        elif path in ASSETS:
            name, kind = ASSETS[path]
            self.send_bytes((WEB / name).read_bytes(), kind)
        elif path == "/api/health":
            self.send_json({"app": "MovieClip", "ready": self.app.ready})
        elif path == "/api/state":
            self.send_json(self.app.state())
        elif path == "/api/job":
            self.send_json(self.app.job_status())
        elif path == "/api/output-directory":
            with self.app.lock:
                directory = str(self.app.last_output_dir or self.app.default_output_dir)
            self.send_bytes(directory.encode("utf-8"), "text/plain; charset=utf-8")
        elif match := re.fullmatch(r"/clip/([a-f0-9]{32})/(media|thumbnail|frame)", path):
            with self.app.use_clip(match[1]) as clip:
                self.get_clip_media(clip, match[2], url.query)
        elif match := re.fullmatch(r"/output/([a-f0-9]{32})", path):
            with self.app.lock:
                file = self.app.outputs.get(match[1])
            if file:
                self.stream_file(file, "application/octet-stream", download=True)
            else:
                self.not_found()
        else:
            self.not_found()

    def get_clip_media(self, clip, kind, query):
        if not clip:
            self.not_found()
        elif kind == "media":
            media_type = MEDIA_TYPES.get(clip.path.suffix.lower()) or mimetypes.guess_type(clip.path)[0]
            self.connection.settimeout(30)
            self.stream_file(clip.path, media_type if media_type and media_type.startswith("video/")
                             else "application/octet-stream")
        elif kind == "thumbnail":
            self.stream_file(clip.workspace / "thumbnail.jpg", "image/jpeg")
        else:
            position = seconds(parse_qs(query).get("t", [0])[0])
            still = frame(clip, max(0, min(position, clip.duration - min(0.15, clip.duration / 2))), 960)
            if still:
                self.send_bytes(still, "image/jpeg")
            else:
                self.not_found()

    def post(self, path):
        if path == "/api/upload":
            name = Path(unquote(self.headers.get("X-File-Name", ""))).name
            length = self.content_length()
            if not name or not length:
                raise StudioError("내용이 있는 영상 파일을 선택해 주세요.")
            self.connection.settimeout(120)
            self.send_json(self.app.import_clip(name, stream=self.rfile, length=length), 201)
            return
        if path not in ("/api/open", "/api/remove", "/api/export", "/api/cancel",
                        "/api/pick-folder", "/api/pick-files", "/api/default-output"):
            self.not_found()
            return
        length = self.content_length()
        if not 0 < length <= 65_536:
            raise StudioError("요청 내용을 읽을 수 없습니다.")
        try:
            data = json.loads(self.rfile.read(length))
        except (ValueError, UnicodeError) as error:
            raise StudioError("요청 내용을 읽을 수 없습니다.") from error
        if not isinstance(data, dict):
            raise StudioError("요청 내용을 읽을 수 없습니다.")
        if path == "/api/open":
            source = local_path(data.get("path"))
            self.send_json(self.app.import_clip(source.name, source=source), 201)
        elif path == "/api/remove":
            if not isinstance(data.get("id"), str):
                raise StudioError("목록에서 영상을 선택해 주세요.")
            self.app.remove(data["id"])
            self.send_json({"ok": True})
        elif path == "/api/export":
            self.send_json(self.app.start_job(data), 202)
        elif path == "/api/cancel":
            self.app.cancel_job(data.get("id"))
            self.send_json(self.app.job_status())
        elif path == "/api/default-output":
            self.send_json({"path": self.app.set_default_output(data.get("path"))})
        elif path == "/api/pick-files":
            if not self.app.file_picker:
                raise StudioError("Windows 파일 선택기를 사용할 수 없습니다.")
            result = subprocess.run([self.app.file_picker, "--pick-files"], capture_output=True,
                                    check=True, timeout=600)
            self.send_json({"paths": result.stdout.decode("utf-8").split("\n") if result.stdout else []})
        elif path == "/api/pick-folder":
            if not self.app.folder_picker:
                raise StudioError("저장 폴더의 전체 경로를 직접 입력해 주세요.")
            try:
                initial = local_path(data.get("path"), directory=True)
            except StudioError:
                initial = self.app.last_output_dir or self.app.default_output_dir
            result = subprocess.run([self.app.folder_picker, "--pick-folder", str(initial)],
                                    capture_output=True, check=True, timeout=600)
            self.send_json({"path": result.stdout.decode("utf-8").strip() or None})

    def content_length(self):
        value = self.headers.get("Content-Length", "")
        if not value.isascii() or not value.isdecimal() or len(value) > 18:
            raise StudioError("파일 크기를 확인할 수 없습니다.")
        return int(value)

    def headers_for(self, status, kind, length, extra=()):
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(length))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'")
        for name, value in extra:
            self.send_header(name, value)
        self.end_headers()

    def send_bytes(self, body, kind, status=200):
        self.headers_for(status, kind, len(body))
        if self.command != "HEAD":
            self.wfile.write(body)

    def send_json(self, value, status=200):
        self.send_bytes(json.dumps(value, ensure_ascii=False).encode("utf-8"),
                        "application/json; charset=utf-8", status)

    def not_found(self):
        self.send_json({"error": "파일이나 작업을 찾을 수 없습니다."}, 404)

    def stream_file(self, path, kind, download=False):
        try:
            file = path.open("rb")
        except FileNotFoundError:
            self.not_found()
            return
        with file:
            file.seek(0, 2)
            size = file.tell()
            start, end, status = 0, size - 1, 200
            headers = [("Accept-Ranges", "bytes")]
            if download:
                headers.append(("Content-Disposition",
                                f"attachment; filename=\"MovieClip{path.suffix}\"; filename*=UTF-8''{quote(path.name)}"))
            requested = self.headers.get("Range")
            if requested:
                match = re.fullmatch(r"bytes=([0-9]{0,18})-([0-9]{0,18})", requested)
                if match and (match[1] or match[2]):
                    if match[1]:
                        start = int(match[1])
                        end = min(end, int(match[2])) if match[2] else end
                    else:
                        start = max(0, size - int(match[2]))
                else:
                    start = size
                if start > end:
                    self.headers_for(416, kind, 0, [("Content-Range", f"bytes */{size}")])
                    return
                status = 206
                headers.append(("Content-Range", f"bytes {start}-{end}/{size}"))
            remaining = end - start + 1
            self.headers_for(status, kind, remaining, headers)
            if self.command == "HEAD":
                return
            file.seek(start)
            while remaining:
                chunk = file.read(min(CHUNK, remaining))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)


def main():
    parser = argparse.ArgumentParser(description="MovieClip 로컬 영상 편집기")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "exports")
    parser.add_argument("--settings-file", type=Path, default=settings_path())
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--exit-with-stdin", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    def stop(*_):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, stop)
    with tempfile.TemporaryDirectory(prefix="movieclip-") as directory:
        app = Workspace(Path(directory), args.output_dir.resolve(), args.settings_file)
        with ThreadingHTTPServer(("127.0.0.1", args.port), StudioHandler) as server:
            server.app = app
            server.verbose = args.verbose
            print(f"MovieClip http://127.0.0.1:{server.server_port}", flush=True)

            def wait_for_launcher():
                sys.stdin.read()
                server.shutdown()

            if args.exit_with_stdin:
                threading.Thread(target=wait_for_launcher, daemon=True).start()
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
            finally:
                if app.job:
                    app.cancel_job(app.job["id"])
                if app.worker:
                    app.worker.join()


if __name__ == "__main__":
    main()
