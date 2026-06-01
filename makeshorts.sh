#!/usr/bin/env bash
set -e

cd '/mnt/c/Users/lucky/Videos/방송/포르자 호라이즌 6'

input_file='다간.mp4'
output_file='다간_short.mp4'

echo y | ffmpeg \
  -ss 00:01:16 \
  -to 00:02:35 \
  -i "$input_file" \
  -filter_complex "\
[0:v]crop=ih*4/3:ih:(iw-ih*4/3)/2:0,scale=1080:810,pad=1080:1920:0:(1920-810)/2:color=black[v]" \
  -map "[v]" \
  -map 0:a:1 \
  -c:v libx264 -preset fast -crf 23 \
  -c:a aac -b:a 128k -ac 2 \
  "$output_file" \
  # -t 32 \
