#!/usr/bin/env bash
set -e

cd '/mnt/c/Users/lucky/Videos/방송/명일방주 엔드필드'

input_file='이게 바로 통합 공업 시스템의 힘이야 관리자.mp4'
output_file='이게 바로 통합 공업 시스템의 힘이야 관리자_short.mp4'

echo y | ffmpeg \
  -ss 00:00:05.5 \
  -i "$input_file" \
  -filter_complex "\
[0:v]crop=ih*4/3:ih:(iw-ih*4/3)/2:0,scale=1080:810,pad=1080:1920:0:(1920-810)/2:color=black[v]" \
  -map "[v]" \
  -map 0:a:1 \
  -c:v libx264 -preset fast -crf 23 \
  -c:a aac -b:a 128k -ac 2 \
  "$output_file" \
  # -t 32 \
