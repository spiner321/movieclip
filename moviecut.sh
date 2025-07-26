cd "/mnt/c/Users/lucky/Videos/방송/동키콩 바난자"

# # part1: 00:55:45 ~ 00:56:55 (1분 10초 = 00:01:10)
# echo y | ffmpeg -ss 00:55:45 -i aaa.mkv -t 00:01:10 -c copy part1.mkv

# # part2: 00:57:55 ~ 00:58:56 (1분 1초 = 00:01:01)
# echo y | ffmpeg -ss 00:57:55 -i aaa.mkv -t 00:01:01 -c copy part2.mkv

# # part3: 01:13:38 ~ 02:07:43 (54분 5초 = 00:54:05)
# echo y | ffmpeg -ss 01:13:38 -i aaa.mkv -t 00:54:05 -c copy part3.mkv

echo y | ffmpeg -i "바난자 수련 1.mkv" -t 2:09:10 -c copy "바난자 수련 1 cut.mkv"