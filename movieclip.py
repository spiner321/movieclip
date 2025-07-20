import os
import ffmpeg

# 1번과 2번 파일 경로
file1 = "/mnt/d/workspace/movieclip/나인 솔즈 6화 (진 엔딩：후예사일(Shooting Star)).mkv"
file2 = "/mnt/d/workspace/movieclip/화면 녹화 중 2025-06-03 183906.mp4"

# file1을 자를 기준 타임스탬프 (HH:MM:SS)
split_ts = "02:51:26"

# 임시 폴더 생성
temp_dir = "temp_parts"
os.makedirs(temp_dir, exist_ok=True)

if __name__ == "__main__":
    # 1) file1 앞부분 추출 → part1.mkv (AV1을 MKV 채로 복사)
    part1_mkv = os.path.join(temp_dir, "part1.mkv")
    # ffmpeg.input(file1, ss=0, to=split_ts).output(
    #     part1_mkv,
    #     c="copy",
    #     **{"fflags": "+genpts", "avoid_negative_ts": "make_zero"}
    # ).run(overwrite_output=True)

    # 2) file1 뒷부분 추출 → part3.mkv
    part3_mkv = os.path.join(temp_dir, "part3.mkv")
    # ffmpeg.input(file1, ss=split_ts).output(
    #     part3_mkv,
    #     c="copy",
    #     **{"fflags": "+genpts", "avoid_negative_ts": "make_zero"}
    # ).run(overwrite_output=True)

    # 3) file2 (H.264 MP4)는 그대로
    part2_mp4 = file2

    # 4) 각 파트를 TS로 remux (AV1은 av1_mp4toannexb, H.264는 h264_mp4toannexb 사용)
    ts_paths = []
    for idx, src in enumerate([part1_mkv, part2_mp4, part3_mkv], start=1):
        ts_out = os.path.join(temp_dir, f"part{idx}.ts")

        # AV1(MKV)인 경우 비디오 필터, H.264(MP4)인 경우 다른 필터
        kwargs = {}
        if src.endswith(".mkv"):
            # AV1 → TS : av1_mp4toannexb 필터 반드시 지정
            kwargs["bsf:v"] = "av1_mp4toannexb"
        else:
            # H.264 → TS : h264_mp4toannexb 필터
            kwargs["bsf:v"] = "h264_mp4toannexb"

        # 오디오는 AAC이므로 TS에 담으려면 aac_adtstoasc 필터 지정
        kwargs["bsf:a"] = "aac_adtstoasc"

        ffmpeg.input(src).output(
            ts_out,
            format="mpegts",
            c="copy",
            **kwargs
        ).run(overwrite_output=True)

        ts_paths.append(ts_out)

    # 5) concat 프로토콜로 TS 세그먼트들을 합쳐서 merged.mp4 생성
    concat_input = "concat:" + "|".join(ts_paths)
    ffmpeg.input(concat_input, format="mpegts").output(
        "merged.mp4",
        c="copy",
        **{"bsf:a": "aac_adtstoasc"}  # MP4 컨테이너에 담을 때 AAC 비트스트림 정합
    ).run(overwrite_output=True)

    print("✅ 최종 merged.mp4 생성 완료")