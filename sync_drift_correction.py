import argparse
import subprocess
import sys

def run_cmd(cmd):
    """Execute a shell command and return its stdout as string."""
    try:
        output = subprocess.check_output(cmd, stderr=subprocess.STDOUT, shell=True)
        return output.decode().strip()
    except subprocess.CalledProcessError as e:
        print(f"Command failed: {e.cmd}\nOutput: {e.output.decode()}", file=sys.stderr)
        sys.exit(1)


def get_media_duration(path):
    """Get total duration of media file (container-level)."""
    cmd = (
        f"ffprobe -v error -show_entries format=duration "
        f"-of default=noprint_wrappers=1:nokey=1 '{path}'"
    )
    return float(run_cmd(cmd))


def get_audio_duration(path):
    """Get duration of the first audio stream, with fallback to TAG:DURATION."""
    # 1) Try stream-level duration
    cmd_stream = (
        f"ffprobe -v error -select_streams a:0 "
        f"-show_entries stream=duration "
        f"-of default=noprint_wrappers=1:nokey=1 '{path}'"
    )
    out = run_cmd(cmd_stream)
    if out:
        try:
            return float(out)
        except ValueError:
            pass
    # 2) Fallback to TAG:DURATION (format HH:MM:SS.micro...)
    cmd_tag = (
        f"ffprobe -v error -select_streams a:0 "
        f"-show_entries stream_tags=DURATION "
        f"-of default=noprint_wrappers=1:nokey=1 '{path}'"
    )
    tag = run_cmd(cmd_tag)
    if not tag:
        print(f"[ERROR] Could not determine audio duration for {path}", file=sys.stderr)
        sys.exit(1)
    parts = tag.split(':')
    if len(parts) != 3:
        print(f"[ERROR] Unexpected TAG:DURATION format: {tag}", file=sys.stderr)
        sys.exit(1)
    hours = int(parts[0])
    minutes = int(parts[1])
    seconds = float(parts[2])
    return hours * 3600 + minutes * 60 + seconds


def get_audio_sample_rate(path):
    """Get sample rate of the first audio stream."""
    cmd = (
        f"ffprobe -v error -select_streams a:0 "
        f"-show_entries stream=sample_rate "
        f"-of default=noprint_wrappers=1:nokey=1 '{path}'"
    )
    return int(run_cmd(cmd))


def main():
    parser = argparse.ArgumentParser(
        description="Auto-correct audio/video drift by adjusting audio playback speed."
    )
    parser.add_argument(
        "-i", "--input", required=True,
        help="Path to input MKV file"
    )
    parser.add_argument(
        "-o", "--output", required=True,
        help="Path for output corrected MKV"
    )
    args = parser.parse_args()

    in_path = args.input
    out_path = args.output

    print("Measuring durations...")
    video_dur = get_media_duration(in_path)
    audio_dur = get_audio_duration(in_path)
    print(f"Video duration: {video_dur:.3f}s")
    print(f"Audio duration: {audio_dur:.3f}s")

    ratio = video_dur / audio_dur
    print(f"Computed speed ratio: {ratio:.6f}")

    # Get audio sample rate
    sr = get_audio_sample_rate(in_path)
    print(f"Audio sample rate: {sr} Hz")

    # Build ffmpeg filter chain
    filter_chain = f"asetrate={sr}*{ratio},aresample={sr}"
    print(f"Applying filter: {filter_chain}")

    ffmpeg_cmd = (
        f"ffmpeg -i '{in_path}' -c:v copy -af \"{filter_chain}\" '{out_path}'"
    )
    print(f"Running: {ffmpeg_cmd}")
    subprocess.call(ffmpeg_cmd, shell=True)

    print("Done. Output saved to", out_path)


if __name__ == "__main__":
    main()
