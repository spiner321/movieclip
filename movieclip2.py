import os
import ffmpeg

# ─── 사용자 설정 ───────────────────────────────────────────────────────────
file1 = "/mnt/d/workspace/movieclip/나인 솔즈 6화 (진 엔딩：후예사일(Shooting Star)).mkv"
file2 = "/mnt/d/workspace/movieclip/화면 녹화 중 2025-06-03 183906.mp4"
split_ts = "02:51:28"            # file1을 쪼갤 기준 시각 (HH:MM:SS)
to = "05:10"
temp_dir = "temp_parts"          # 임시 폴더
merged_output = "merged_av1.mkv" # 최종 AV1/MKV 출력 파일
# ──────────────────────────────────────────────────────────────────────────

os.makedirs(temp_dir, exist_ok=True)

# 1) file1 → part1.mkv, part3.mkv (AV1 복사)
part1_mkv = os.path.join(temp_dir, "part1.mkv")
part3_mkv = os.path.join(temp_dir, "part3.mkv")

# print("1️⃣ file1 앞부분(0~split_ts)과 뒷부분(split_ts~끝)을 MKV(AV1)로 분리합니다...")
# ffmpeg.input(file1, ss=0, to=split_ts).output(
#     part1_mkv,
#     c="copy",
#     **{"fflags": "+genpts", "avoid_negative_ts": "make_zero"}
# ).run(overwrite_output=True)
# print(f"   • part1.mkv 생성됨: {part1_mkv}")

# ffmpeg.input(file1, ss=split_ts).output(
#     part3_mkv,
#     c="copy",
#     **{"fflags": "+genpts", "avoid_negative_ts": "make_zero"}
# ).run(overwrite_output=True)
# print(f"   • part3.mkv 생성됨: {part3_mkv}")

# 2) file2(MP4/H.264) → part2_av1.mkv (AV1 재인코딩)
# part2_av1 = os.path.join(temp_dir, "part2_av1.mkv")
part2_av1 = "/mnt/d/workspace/movieclip/temp_parts/part2_av1.mkv"
print("2️⃣ file2(MP4/H.264) → AV1 재인코딩 시작 (av1_nvenc 사용)...")
# ‣ libaom-av1 인코딩은 매우 느립니다.
# ‣ crf: 0~63(낮을수록 고화질). 원본 품질과 비슷하게 두려면 30~35 사이를 시도해보세요.
# ‣ b:v="0"을 쓰면 CRF 모드로 동작하며, 고정 비트레이트 대신 품질 우선 인코딩.
(
    ffmpeg
    .input(file2, ss=0, to=to)
    .output(
        part2_av1,
        vcodec="av1_nvenc",
        preset="p6",      # p1~p7: 숫자가 클수록 화질↑, 속도↓
        acodec="copy"
    )
    .run(overwrite_output=True)
)
print(f"   • part2_av1.mkv 생성됨: {part2_av1}")

# 3) 세 파트(모두 AV1/MKV) → concat_list.txt 생성
concat_txt = os.path.join(temp_dir, "concat_list.txt")
with open(concat_txt, "w", encoding="utf-8") as f:
    # FFmpeg concat demuxer는 파일 이름 앞에 "file '<경로>'" 형식을 요구합니다.
    f.write(f"file '{os.path.abspath(part1_mkv)}'\n")
    f.write(f"file '{os.path.abspath(part2_av1)}'\n")
    f.write(f"file '{os.path.abspath(part3_mkv)}'\n")
print(f"3️⃣ concat_list.txt 생성됨: {concat_txt}")

# 4) concat demuxer로 무손실(remux) 이어붙이기 → merged_av1.mkv
print("4️⃣ concat demuxer를 이용해 세 AV1/MKV를 –c copy로 이어붙입니다...")
(
    ffmpeg
    .input(concat_txt, format="concat", safe=0)
    .output(
        merged_output,
        c="copy"
    )
    .run(overwrite_output=True)
)
print(f"✅ 최종 merged_av1.mkv 생성 완료: {merged_output}")
