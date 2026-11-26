#!/usr/bin/env bash
set -euo pipefail

cd "/mnt/c/Users/lucky/Videos/방송/요시와 신기한 도감"

ffmpeg -n -hwaccel cuda -hwaccel_output_format cuda -i "1화.mp4" \
    -map 0 -vf "scale_cuda=-2:1440:interp_algo=lanczos" -c copy -c:v av1_nvenc -preset p6 -rc constqp -qp 15 "1화_1440p_lanczos_av1.mp4"

ffmpeg -n -hwaccel cuda -hwaccel_output_format cuda -i "2화.mp4" \
    -map 0 -vf "scale_cuda=-2:1440:interp_algo=lanczos" -c copy -c:v av1_nvenc -preset p6 -rc constqp -qp 15 "2화_1440p_lanczos_av1.mp4"
