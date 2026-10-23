#!/usr/bin/env bash
# Обложку V4 — первым кадром ролика: ./reel/poster_intro.sh <mp4> <jpg>
# У Shorts YouTube в Studio и в ленте показывает кадр из видео, а обложку через API — только в поиске
# и на вкладке «Видео» (24.10.2026). Поэтому jpg кладём поверх первых POSTER_INTRO_S секунд (1 с):
# длина и звук не меняются, кадр с обложкой можно выбрать превью в приложении YouTube.
set -euo pipefail
MP4="${1:?mp4}"; JPG="${2:?jpg}"; S="${POSTER_INTRO_S:-1.0}"
[ -s "$JPG" ] || { echo "poster_intro.sh: нет $JPG" >&2; exit 1; }
ffmpeg -y -v error -i "$MP4" -loop 1 -i "$JPG" -filter_complex \
  "[1:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,format=yuv420p[p];[0:v][p]overlay=0:0:enable='lt(t,$S)':shortest=1,format=yuv420p[v]" \
  -map "[v]" -map '0:a?' -c:v libx264 -preset medium -crf 18 -r 30 -c:a copy -movflags +faststart "$MP4.poster.mp4"
mv -f "$MP4.poster.mp4" "$MP4"
