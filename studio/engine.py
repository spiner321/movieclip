import json
import math
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path


PROCESS_FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class StudioError(Exception):
    pass


def seconds(value):
    try:
        result = float(value)
        if math.isfinite(result):
            return result
    except (TypeError, ValueError):
        pass
    raise StudioError("시간을 확인해 주세요.")


def ff_time(value):
    return f"{value:.6f}"


@dataclass
class Clip:
    id: str
    path: Path
    name: str
    workspace: Path
    duration: float
    streams: list
    video: dict
    audio: list

    def describe(self):
        width, height = self.video["width"], self.video["height"]
        rotation = next((item.get("rotation", 0) for item in self.video.get("side_data_list", [])
                         if "rotation" in item), 0)
        if abs(rotation) % 180 == 90:
            width, height = height, width
        return {
            "id": self.id, "name": self.name, "duration": self.duration,
            "width": width, "height": height, "codec": self.video.get("codec_name", ""),
            "audio": [
                {"index": index, "codec": track.get("codec_name", ""),
                 "title": track.get("tags", {}).get("title", ""),
                 "language": track.get("tags", {}).get("language", "")}
                for index, track in enumerate(self.audio)
            ],
            "thumbnail": (self.workspace / "thumbnail.jpg").is_file(),
        }


def probe(clip_id, path, name, workspace):
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-protocol_whitelist", "file,pipe",
             "-show_streams", "-show_format", "-of", "json", str(path)],
            capture_output=True, check=True, timeout=40, creationflags=PROCESS_FLAGS,
        )
        info = json.loads(result.stdout)
    except (subprocess.SubprocessError, ValueError) as error:
        raise StudioError("영상 정보를 읽을 수 없습니다. 파일 형식과 접근 권한을 확인해 주세요.") from error
    streams = info.get("streams", [])
    video = next((stream for stream in streams if stream.get("codec_type") == "video"
                  and not stream.get("disposition", {}).get("attached_pic")
                  and stream.get("width") and stream.get("height")), None)
    if video is None:
        raise StudioError("파일에 편집할 동영상 트랙이 없습니다.")
    duration = seconds(info.get("format", {}).get("duration") or video.get("duration"))
    if duration <= 0:
        raise StudioError("영상의 재생 시간을 확인할 수 없습니다.")
    audio = [track for track in streams if track.get("codec_type") == "audio"]
    return Clip(clip_id, path, name, workspace, duration, streams, video, audio)


def frame(clip, position, width):
    process = subprocess.run(
        ["ffmpeg", "-v", "error", "-nostdin", "-ss", ff_time(position),
         "-protocol_whitelist", "file,pipe", "-i", str(clip.path),
         "-map", f"0:{clip.video['index']}", "-frames:v", "1",
         "-vf", f"scale={width}:-2", "-threads", "1", "-c:v", "mjpeg",
         "-f", "image2pipe", "pipe:1"],
        capture_output=True, check=True, timeout=20, creationflags=PROCESS_FLAGS,
    )
    return process.stdout


def local_path(value, directory=False):
    prompt = ("저장 폴더의 전체 경로를 입력해 주세요." if directory
              else "영상 파일을 찾을 수 없습니다. 파일의 전체 경로를 확인해 주세요.")
    if not isinstance(value, str):
        raise StudioError(prompt)
    value = value.strip().strip('"')
    if os.name != "nt" and re.match(r"^(?:[a-zA-Z]:[\\/]|\\\\)", value):
        if shutil.which("wslpath"):
            result = subprocess.run(["wslpath", "-u", value], capture_output=True,
                                    text=True, timeout=5)
            if result.returncode == 0:
                value = result.stdout.rstrip("\r\n")
    try:
        path = Path(value)
        if path.is_absolute() and (directory or path.is_file()):
            return path.resolve()
    except (OSError, ValueError):
        pass
    raise StudioError(prompt)


def export_name(value):
    if not isinstance(value, str):
        raise StudioError("파일 이름을 입력해 주세요.")
    name = re.sub(r"\.(mp4|mkv)$", "", value.strip(), flags=re.IGNORECASE).rstrip(" .")
    if (not name or len(name.encode("utf-8")) > 200
            or re.search(r'[<>:"/\\|?*\x00-\x1f]', name)
            or re.fullmatch(r"(?:CON|PRN|AUX|NUL|COM[1-9¹²³]|LPT[1-9¹²³])(?:\..*)?", name, re.I)):
        raise StudioError("파일 이름을 확인해 주세요. 특수 문자를 빼거나 이름을 짧게 써 주세요.")
    return name


def input_args(path):
    return ["-protocol_whitelist", "file,pipe", "-i", str(path)]


def signature(clip):
    fields = ("codec_type", "codec_name", "time_base", "width", "height", "pix_fmt",
              "sample_rate", "channels", "channel_layout")
    return [tuple(stream.get(field) for field in fields) for stream in clip.streams]


def audio_map(clip, value):
    if value == "none":
        return []
    if value == "all":
        return ["-map", "0:a?"]
    if type(value) is not int or not 0 <= value < len(clip.audio):
        raise StudioError("영상에 포함된 오디오 트랙을 선택해 주세요.")
    return ["-map", f"0:a:{value}"]


def render_plan(options, clips, folder):
    """Return commands, staged output paths, and their expected durations."""
    mode = options.get("mode")
    extension = options.get("format")
    if extension not in ("mp4", "mkv") or (mode == "shorts" and extension != "mp4"):
        raise StudioError("지원하는 출력 형식을 선택해 주세요.")
    name = export_name(options.get("name"))
    container = ["-movflags", "+faststart"] if extension == "mp4" else []

    def output(args, duration, suffix=""):
        path = folder / f"{name}{suffix}.{extension}"
        return args + container + [str(path)], path, duration

    if mode == "concat":
        if len(clips) < 2:
            raise StudioError("이어 붙일 영상을 두 개 이상 선택해 주세요.")
        original = signature(clips[0])
        if any(signature(clip) != original for clip in clips[1:]):
            raise StudioError("선택한 영상의 코덱, 해상도 또는 트랙 구성이 다릅니다. "
                              "같은 설정으로 녹화한 영상을 선택해 주세요.")
        playlist = folder / "inputs.ffconcat"
        # FFconcat uses its own single-quote escaping and parses each physical line.
        entries = []
        for clip in clips:
            path = clip.path.as_posix()
            if "\n" in path or "\r" in path:
                raise StudioError("이어 붙일 파일의 경로에서 줄바꿈을 제거해 주세요.")
            quoted = path.replace("'", "'\\''")
            entries.append(f"file '{quoted if os.name != 'nt' else 'file:' + quoted}'")
        playlist.write_text("ffconcat version 1.0\n" + "\n".join(entries) + "\n", encoding="utf-8")
        return [output(["-f", "concat", "-safe", "0", *input_args(playlist),
                        "-map", "0", "-c", "copy"], sum(clip.duration for clip in clips))]

    if len(clips) != 1 or mode not in ("fast", "precise", "split", "shorts"):
        raise StudioError("편집할 영상을 선택해 주세요.")
    clip = clips[0]
    start = seconds(options.get("start"))
    if mode == "split":
        if not 0 < start < clip.duration:
            raise StudioError("분할 위치는 영상의 시작과 끝 사이여야 합니다.")
        return [
            output([*input_args(clip.path), "-t", ff_time(start), "-map", "0", "-c", "copy"],
                   start, "_앞부분"),
            output(["-ss", ff_time(start), *input_args(clip.path), "-map", "0", "-c", "copy"],
                   clip.duration - start, "_뒷부분"),
        ]
    end = seconds(options.get("end"))
    if not 0 <= start < end <= clip.duration + 0.0005:
        raise StudioError("시작과 종료 시간을 영상 길이 안에서 선택해 주세요.")
    duration = min(end, clip.duration) - start
    base = ["-ss", ff_time(start), *input_args(clip.path), "-t", ff_time(duration),
            "-map", f"0:{clip.video['index']}", *audio_map(clip, options.get("audio"))]
    if mode == "fast":
        # Keep the leading keyframe visible instead of hiding the pre-roll in an MP4 edit list.
        return [output(base + ["-c", "copy", "-avoid_negative_ts", "make_non_negative"], duration)]

    filters = "scale=trunc(iw/2)*2:trunc(ih/2)*2"
    audio = ["-c:a", "aac", "-b:a", "192k"]
    if mode == "shorts":
        filters = ("crop='trunc(min(iw,ih*4/3)/2)*2':'trunc(ih/2)*2',"
                   "scale=1080:810:force_original_aspect_ratio=decrease:force_divisible_by=2,"
                   "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black,setsar=1")
        audio = ["-c:a", "aac", "-b:a", "128k", "-ac", "2"]
    return [output(base + ["-vf", filters, "-c:v", "libx264", "-preset", "fast",
                           "-crf", "23", "-pix_fmt", "yuv420p", *audio], duration)]


def render(args, duration, update, manage_process):
    with tempfile.TemporaryFile() as log:
        command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin",
                   "-progress", "pipe:1", "-nostats", *args]
        with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=log, text=True,
                              creationflags=PROCESS_FLAGS) as process:
            manage_process(process)
            for line in process.stdout:
                if line.startswith("out_time_us="):
                    value = line.strip().partition("=")[2]
                    if value.lstrip("-").isdigit():
                        update(max(0, min(1, int(value) / 1_000_000 / duration)))
            result = process.wait()
        manage_process(None)
        if result:
            log.seek(max(0, log.tell() - 3000))
            detail = log.read().decode("utf-8", errors="replace").strip()
            raise StudioError(detail or "FFmpeg에서 내보내기를 완료하지 못했습니다.")


def publish(staged, target_dir):
    # Reserve each destination exclusively before publishing any of the outputs.
    reserved = []
    try:
        for path in staged:
            candidate = target_dir / path.name
            number = 2
            while True:
                try:
                    with candidate.open("xb"):
                        pass
                    reserved.append(candidate)
                    break
                except FileExistsError:
                    candidate = target_dir / f"{path.stem} ({number}){path.suffix}"
                    number += 1
        for source, destination in zip(staged, reserved):
            source.replace(destination)
    except OSError:
        for destination in reserved:
            destination.unlink(missing_ok=True)
        raise
    return reserved
