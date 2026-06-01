#!/usr/bin/env bash
set -euo pipefail

cd "/mnt/c/Users/lucky/Videos/방송/요시와 신기한 도감"

ffmpeg -n -i "1화.mp4" -map 0 -vf "scale=-2:1440:flags=lanczos" -c copy -c:v libx264 -preset slow -crf 18 "1화_1440p_lanczos.mp4"
ffmpeg -n -i "2화.mp4" -map 0 -vf "scale=-2:1440:flags=lanczos" -c copy -c:v libx264 -preset slow -crf 18 "2화_1440p_lanczos.mp4"
