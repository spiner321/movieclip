#!/usr/bin/env bash
set -e

cd "/mnt/c/Users/lucky/Videos/방송/포르자 호라이즌 6"

# 정밀하게 자르기
# echo y | ffmpeg -i "1화.mp4" -ss 06:15:10 -to 06:19:50 -c copy "건담과 레이스.mp4"

# 빠르게 자르기
ffmpeg -y -ss 06:15:00 -i "1화.mp4" -t 00:05:00 -c copy "건담과 레이스_대략.mp4"