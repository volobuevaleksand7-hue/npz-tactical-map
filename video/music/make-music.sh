#!/usr/bin/env bash
# Фоновая музыка ролика — синтез из ничего, только ffmpeg (без numpy и скачиваний).
#   bash video/music/make-music.sh          # создаёт gen-*.wav рядом, если их нет
#   bash video/music/make-music.sh --force  # перегенерировать
# Вызывается сам из build.py mix, когда в music/ нет ни одного трека. Результат в git
# не кладётся (.gitignore) — детерминирован, на любой машине получится тот же звук.
#
# Три «новостных/тактических» эмбиент-лупа по 16 тактов (36–40 с), без мелодии:
# пульсирующий бас восьмыми (с обертонами — чтобы был слышен на телефоне), глухая бочка
# на 1 и 3, тихие хэты на слабые доли, медленный пэд двух аккордов с перетеканием,
# редкий «радарный» пинг с эхом. Громкость нормализована на ~-20 LUFS; в ролике
# build.py ещё прибирает её до фона (volume 0.32 + sidechain под эффекты).
set -euo pipefail
cd "$(dirname "$0")"
FORCE=0; [ "${1:-}" = "--force" ] && FORCE=1
command -v ffmpeg >/dev/null || { echo "make-music.sh: нужен ffmpeg" >&2; exit 2; }
SR=48000

# track <имя> <bpm> <бас1 Гц> <бас2 Гц> "<аккорд A: 3 частоты>" "<аккорд B: 3 частоты>" <пинг Гц>
track() {
  local name=$1 bpm=$2 f1=$3 f2=$4 ping=$7
  local -a A=($5) B=($6)
  local out="gen-$name.wav"
  if [ -s "$out" ] && [ $FORCE = 0 ]; then echo "есть $out"; return; fi
  local b; b=$(awk -v x="$bpm" 'BEGIN{printf "%.6f", 60/x}')       # доля, с
  local E; E=$(awk -v x="$b" 'BEGIN{printf "%.6f", x/2}')           # восьмая
  local L; L=$(awk -v x="$b" 'BEGIN{printf "%.6f", x*64}')          # 16 тактов
  local H; H=$(awk -v x="$b" 'BEGIN{printf "%.6f", x*32}')          # смена аккорда — каждые 8 тактов

  # бас: восьмые, сильные доли громче; первые 8 тактов f1, следующие 8 — f2;
  # атака 1-exp(-200τ) — нулевая амплитуда на стыке нот, без щелчков
  local F="if(lt(mod(t,$L),$H),$f1,$f2)"
  local bass="(0.55+0.45*eq(mod(floor(t/$E),2),0))*exp(-3.2*mod(t,$E)/$E)*(1-exp(-200*mod(t,$E)))*(sin(2*PI*$F*t)+0.5*sin(4*PI*$F*t)+0.25*sin(6*PI*$F*t))"
  # бочка на 1 и 3: синус с падающей частотой 160->45 Гц
  local k="mod(t,2*$b)"
  local kick="exp(-9*$k)*sin(2*PI*(45*$k+4.4*(1-exp(-25*$k))))"
  # хэты на слабые восьмые
  local hat="(random(0)*2-1)*exp(-70*mod(t+$E,$b))"
  # пэд: аккорд A перетекает в B и обратно (косинус с периодом 16 тактов — луп бесшовный)
  local w="(0.5-0.5*cos(2*PI*t/$L))"
  local pa="(sin(2*PI*${A[0]}*t)+sin(2*PI*${A[0]}*1.004*t)+sin(2*PI*${A[1]}*t)+sin(2*PI*${A[1]}*0.997*t)+0.7*sin(2*PI*${A[2]}*t))"
  local pb="(sin(2*PI*${B[0]}*t)+sin(2*PI*${B[0]}*1.004*t)+sin(2*PI*${B[1]}*t)+sin(2*PI*${B[1]}*0.997*t)+0.7*sin(2*PI*${B[2]}*t))"
  local pad="(1-$w)*$pa+$w*$pb"
  # радарный пинг раз в 4 такта (на второй доле)
  local p="mod(t-$b,16*$b)"
  local pingx="gte(t,$b)*exp(-7*$p)*sin(2*PI*$ping*t)"

  ffmpeg -hide_banner -loglevel error -y \
    -f lavfi -i "aevalsrc='$bass':s=$SR:d=$L" \
    -f lavfi -i "aevalsrc='$kick':s=$SR:d=$L" \
    -f lavfi -i "aevalsrc='$hat':s=$SR:d=$L" \
    -f lavfi -i "aevalsrc='$pad':s=$SR:d=$L" \
    -f lavfi -i "aevalsrc='$pingx':s=$SR:d=$L" \
    -f lavfi -i "anoisesrc=c=brown:a=0.5:s=$SR:d=$L:seed=7" \
    -filter_complex "\
[0:a]lowpass=f=420,volume=0.55[ba];\
[1:a]lowpass=f=200,volume=0.75[ki];\
[2:a]highpass=f=7000,volume=0.10[hh];\
[3:a]lowpass=f=1400,volume=0.07,tremolo=f=0.25:d=0.3,aecho=0.8:0.6:180|370:0.35|0.22[pd];\
[4:a]highpass=f=500,volume=0.06,aecho=0.8:0.7:$(awk -v x="$E" 'BEGIN{printf "%d", x*1000}')|$(awk -v x="$b" 'BEGIN{printf "%d", x*1000}'):0.45|0.25[pg];\
[5:a]lowpass=f=300,highpass=f=40,volume=0.05[rn];\
[ba][ki][hh][pd][pg][rn]amix=inputs=6:normalize=0,\
atrim=0:$L,aformat=channel_layouts=stereo,extrastereo=m=1.0,\
loudnorm=I=-20:TP=-3:LRA=11,aresample=$SR,afade=t=in:st=0:d=0.02\
" -ac 2 -ar $SR -c:a pcm_s16le "$out"
  echo "создан $out ($bpm BPM, $(awk -v x="$L" 'BEGIN{printf "%.1f", x}') с)"
}

# ля-минорный «сводка»: A1/E1 бас, Am -> Fmaj7-ish
track svodka 96 55 43.65 "220 261.63 329.63" "174.61 220 261.63" 1320
# ре-минорный «радар»: D2/Bb1, Dm -> Bbmaj
track radar 104 73.42 58.27 "293.66 349.23 440" "233.08 293.66 349.23" 1568
# ми-минорный «фронт»: E1/C2, Em(add9) -> Cmaj
track front 100 41.2 65.41 "164.81 246.94 369.99" "130.81 196 329.63" 1175
