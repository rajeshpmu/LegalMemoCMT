yt-dlp \                  
  --remote-components ejs:npm \
  --cookies-from-browser chrome \
  -f "137+140" \
  --merge-output-format mp4 \
  -o "data/phase2/clancy/clancy_shah_full_testimony.%(ext)s" \
  "https://www.youtube.com/watch?v=sHUdRcABC-Q"


echo "get transcript"
yt-dlp \
  --remote-components ejs:npm \
  --cookies-from-browser chrome \
  --list-subs \
  "https://www.youtube.com/watch?v=sHUdRcABC-Q"

echo "caption "

yt-dlp \
  --remote-components ejs:npm \
  --cookies-from-browser chrome \
  --write-auto-subs \
  --sub-langs "en" \
  --sub-format vtt \
  --skip-download \
  -o "data/phase2/clancy/clancy_shah_full_testimony.%(ext)s" \
  "https://www.youtube.com/watch?v=sHUdRcABC-Q"

echo "Extract 16-kHz mono WAV"
ffmpeg \
  -i data/phase2/clancy/clancy_shah_full_testimony.mp4 \
  -vn -ac 1 -ar 16000 -c:a pcm_s16le \
  data/phase2/clancy/clancy_shah_full_testimony.wav
