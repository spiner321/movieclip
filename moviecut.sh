cd "/mnt/c/Users/lucky/Videos/방송/하이파이 러쉬"

# # 1화 앞부분: 00:00:00 ~ 00:02:01
# echo y | ffmpeg -i "1화.mp4" -to 00:02:01 -c copy "1화_part1.mp4"

# # 1화 뒷부분: 00:06:18 ~ 끝
# echo y | ffmpeg -ss 00:06:18 -i "1화.mp4" -c copy "1화_part2.mp4"

echo y | ffmpeg -i "오프닝.mp4" -to 00:04:17 -c copy "오프닝_part1.mp4"
