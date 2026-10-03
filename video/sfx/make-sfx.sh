#!/usr/bin/env bash
# Синтез звуковых эффектов ролика из ничего — только ffmpeg, без скачиваний.
# Результат (whoosh/impact/click.wav) закоммичен; перегенерировать нужно только
# если захотелось другой звук:  bash video/sfx/make-sfx.sh
set -euo pipefail
cd "$(dirname "$0")"
FF=(ffmpeg -hide_banner -loglevel error -y)

# Вжух на смене сцен: розовый шум, огибающая sin² и восходящий «свист»,
# полосовой фильтр — без резких щелчков на краях.
"${FF[@]}" -f lavfi -i "aevalsrc='(random(0)*2-1)*pow(sin(PI*t/0.75),2)*0.7 + 0.18*sin(2*PI*(180*t+700*t*t))*pow(sin(PI*t/0.75),2)':s=48000:d=0.75" \
  -af "highpass=f=250,lowpass=f=4200,aecho=0.6:0.4:35:0.25,volume=0.9,afade=t=out:st=0.6:d=0.15" \
  -ac 2 -c:a pcm_s16le whoosh.wav

# Удар на появлении цифры: падающий по частоте низкий синус + короткая шумовая атака.
"${FF[@]}" -f lavfi -i "aevalsrc='0.95*sin(2*PI*(70*t-22*t*t))*exp(-5*t) + 0.45*(random(0)*2-1)*exp(-45*t)':s=48000:d=1.3" \
  -af "lowpass=f=1800,volume=0.9,afade=t=out:st=1.1:d=0.2" \
  -ac 2 -c:a pcm_s16le impact.wav

# Тихий щелчок на появлении карточки.
"${FF[@]}" -f lavfi -i "aevalsrc='0.5*sin(2*PI*2100*t)*exp(-90*t) + 0.25*(random(0)*2-1)*exp(-220*t)':s=48000:d=0.09" \
  -af "highpass=f=600,volume=0.55" \
  -ac 2 -c:a pcm_s16le click.wav

ls -la whoosh.wav impact.wav click.wav
