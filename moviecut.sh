cd "/mnt/c/Users/lucky/Videos/방송/"

## 영상 단순 컷팅 (1단계) ##
# echo y | ffmpeg -i "2~3.mkv" -ss 00:00:00 -t 07:22:33 -c copy "2화.mkv"
# echo y | ffmpeg -i "2~3.mkv" -ss 07:22:45 -c copy "3화.mkv"

# 2화 (0:00:00 ~ 7:22:33)
# echo y | ffmpeg -ss 00:00:00 -i "2~3.mkv" -t 07:22:33 -c copy "2화.mkv"

# 3화 (7:22:45 ~ 끝까지)
# echo y | ffmpeg -ss 06:35 -i "2025-10-09 21-50-59.mp4" -c copy "셀레기오스.mp4"



## 영상 정밀 컷팅 (2단계) ##
# 1단계: 근처까지만 빠르게 잘라 임시 파일 생성
# echo y | ffmpeg -ss 00:06:00 -i "2025-10-09 21-50-59.mp4" -c copy tmp.mp4

# 2단계: 정확히 원하는 시점부터 다시 정밀 컷
echo y | ffmpeg -i tmp.mp4 -ss 00:00:37 -c copy "셀레기오스.mp4"
