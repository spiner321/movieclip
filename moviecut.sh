cd "/mnt/c/Users/lucky/Videos/방송/하이파이 러쉬"

# 1화 앞부분: 00:00:00 ~ 00:02:01
echo y | ffmpeg -i "3-1.mp4" -to 00:16:00 -c copy "3-1_part1.mp4"

# 1화 뒷부분: 00:06:18 ~ 끝
echo y | ffmpeg  -i "1화.mp4" -ss 00:06:18-c copy "1화_part2.mp4"