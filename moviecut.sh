#!/usr/bin/env bash
set -e

cd "/mnt/c/Users/lucky/Videos/방송/포코피아"

# 1.mp4 -> 2개 파일로 분할
# echo y | ffmpeg -i "1화.mp4" -to 2:43 -c copy "1-1.mp4"

# 2) 01:14:51 ~ 04:15:36
echo y | ffmpeg -i "1화.mp4" -ss 11:53 -c copy "1-2.mp4"

# 2) 01:14:51 ~ 04:15:36
# echo y | ffmpeg -i "1화.mp4" -ss 11:55 -to 04:15:36 -c copy "1-2.mp4"
