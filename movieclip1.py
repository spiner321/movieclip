import os
import ffmpeg

# ─── 사용자 설정 ─────────────────────────────────────────────────
file1 = "/mnt/d/workspace/movieclip/나인 솔즈 6화 (진 엔딩：후예사일(Shooting Star)).mkv"
file2 = "/mnt/d/workspace/movieclip/화면 녹화 중 2025-06-03 183906.mp4"
# split_ts = "02:51:26"   # file1을 나눌 기준 시각(HH:MM:SS)
split_ts = "02:26"   # file1을 나눌 기준 시각(HH:MM:SS)
to = "05:00"  # file1을 나눌 기준 시각(HH:MM:SS) - 이 부분은 사용되지 않음
temp_dir = "temp_parts" # 임시 폴더
merged_output = "merged.mp4"
# ─────────────────────────────────────────────────────────────────

os.makedirs(temp_dir, exist_ok=True)

# 1) file1을 split_ts 기준으로 앞/뒤 MKV(AV1)로 분리
part1_mkv = os.path.join(temp_dir, "part1.mkv")
part3_mkv = os.path.join(temp_dir, "part3.mkv")

ffmpeg.input(file1, ss=0, to=split_ts).output(
    part1_mkv,
    c="copy",
    **{"fflags": "+genpts", "avoid_negative_ts": "make_zero"}
).run(overwrite_output=True)
print(f"✅ part1.mkv 생성: {part1_mkv}")

ffmpeg.input(file1, ss=split_ts, to=to).output(
    part3_mkv,
    c="copy",
    **{"fflags": "+genpts", "avoid_negative_ts": "make_zero"}
).run(overwrite_output=True)
print(f"✅ part3.mkv 생성: {part3_mkv}")

# 2) part1.mkv(AV1) → part1_h264.mp4 (H.264 재인코딩)
part1_h264 = os.path.join(temp_dir, "part1_h264.mp4")
ffmpeg.input(part1_mkv).output(
    part1_h264,
    vcodec="libx264",   # H.264 코덱
    crf=18,             # 품질: 0~51, 낮을수록 고화질 (18~20 권장)
    preset="slow",      # 인코딩 속도/품질 균형 (ultrafast/medium/slow 중 선택)
    acodec="copy"       # 오디오는 기존 AAC 그대로 복사
).run(overwrite_output=True)
print(f"✅ part1_h264.mp4 생성: {part1_h264}")

# 3) part3.mkv(AV1) → part3_h264.mp4 (H.264 재인코딩)
part3_h264 = os.path.join(temp_dir, "part3_h264.mp4")
ffmpeg.input(part3_mkv).output(
    part3_h264,
    vcodec="libx264",
    crf=18,
    preset="slow",
    acodec="copy"
).run(overwrite_output=True)
print(f"✅ part3_h264.mp4 생성: {part3_h264}")

# 4) file2(MP4/H.264)는 그대로 사용
part2_h264 = file2
print(f"ℹ️ part2_h264 = {part2_h264}")

# 5) concat demuxer용 리스트 파일 생성 (절대경로 or 상대경로 상관없음)
concat_txt = os.path.join(temp_dir, "concat_list.txt")
with open(concat_txt, "w", encoding="utf-8") as f:
    # 반드시 “file '경로'” 형태로 적어야 합니다.
    f.write(f"file '{os.path.abspath(part1_h264)}'\n")
    f.write(f"file '{os.path.abspath(part2_h264)}'\n")
    f.write(f"file '{os.path.abspath(part3_h264)}'\n")
print(f"✅ concat_list.txt 생성: {concat_txt}")

# 6) FFmpeg concat demuxer로 MP4/H.264 3개를 –c copy로 붙여서 merged.mp4 생성
ffmpeg.input(concat_txt, format="concat", safe=0).output(
    merged_output,
    c="copy"
).run(overwrite_output=True)

print("✅ 최종 merged.mp4 생성 완료:", merged_output)