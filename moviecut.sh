#!/usr/bin/env bash
set -e

cd "/mnt/d/방송 영상/스파이더맨"

# 정밀하게 자르기
# echo y | ffmpeg -i "1화.mp4" -ss 06:15:10 -to 06:19:50 -c copy "건담과 레이스.mp4"

# 빠르게 자르기
ffmpeg -y -ss 03:12:30 -i "1화.mp4" -t 00:02:00 \
  -map 0:v:0 -map 0:a:2 -c copy "스탠 리.mp4"



# #!/usr/bin/env bash
# set -e

# cd "/mnt/c/Users/lucky/Videos/방송/포르자 호라이즌 6"

# # 4화를 03:37:50 기준으로 빠르게 분할한다.
# # 스트림 복사이므로 분할 지점은 인접 키프레임 기준으로 맞춰질 수 있다.
# split_at="03:37:50"
# input="4화.mp4"

# ffmpeg -n -i "$input" -t "$split_at" -map 0 -c copy "4화_앞부분.mp4"
# ffmpeg -n -ss "$split_at" -i "$input" -map 0 -c copy "4화_뒷부분.mp4"
