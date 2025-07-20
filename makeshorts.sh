echo y | ffmpeg -i part1.mkv -i part2.mkv -filter_complex "\
[0:v][1:v]concat=n=2:v=1:a=0[v]; \
[0:a][1:a]concat=n=2:v=0:a=1[a]; \
[v]scale=1080:-1,pad=1080:1080:0:(1080-ih)/2:color=black[vo]" \
 -map "[vo]" -map "[a]" \
 -c:v libx264 -preset fast -crf 23 \
 -c:a aac -b:a 128k \
 shorts_square.mp4
