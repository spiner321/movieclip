#!/usr/bin/env bash
set -e

cd '/mnt/c/Users/lucky/Videos/방송/몬스터 헌터 스토리즈 3'

input_file='7화 (완).mp4'
output_file='7화_1080x1920_short.mp4'

echo y | ffmpeg \
  -ss 1:48:18 \
  -t 38 \
  -i "$input_file" \
  -filter_complex "\
[0:v]crop=ih*4/3:ih:(iw-ih*4/3)/2:0,scale=1080:810,pad=1080:1920:0:(1920-810)/2:color=black[v]" \
  -map "[v]" \
  -map 0:a:1 \
  -c:v libx264 -preset fast -crf 23 \
  -c:a aac -b:a 128k -ac 2 \
  "$output_file"
