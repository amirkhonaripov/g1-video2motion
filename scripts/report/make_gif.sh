#!/bin/bash
# Side-by-side GIF: make_gif.sh <out.gif> <input video or -> <label> <video> [<label> <video> ...]
# "-" leaves out the input panel (clips that can't be redistributed). Panels that stop early freeze.
set -e
OUT=$1; INPUT=$2; shift 2
FONT=$(fc-match -f "%{file}" DejaVuSans)
H=240
inputs=(); filters=(); n=0
add() {  # add <video> <label>
  inputs+=(-i "$1")
  label="drawtext=fontfile=$FONT:text='$2':x=8:y=8:fontsize=15:fontcolor=white:box=1:boxcolor=black@0.5"
  filters+=("[$n:v]tpad=stop_mode=clone:stop_duration=600,fps=8,scale=-2:$H,$label[v$n]")
  n=$((n + 1))
}
[ "$INPUT" != - ] && add "$INPUT" "Input video"
while [ $# -gt 0 ]; do add "$2" "$1"; shift 2; done
stack=$(for i in $(seq 0 $((n - 1))); do printf "[v%d]" $i; done)
len=$(for v in "${inputs[@]}"; do
  [ "$v" != -i ] && ffprobe -v error -show_entries format=duration -of csv=p=0 "$v"
done | sort -g | tail -1)
palette="split[a][b];[a]palettegen=max_colors=48:stats_mode=diff[p];"
palette+="[b][p]paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle"
graph="$(IFS=';'; echo "${filters[*]}");${stack}hstack=$n:shortest=1,$palette"
ffmpeg -v error -y "${inputs[@]}" -filter_complex "$graph" -t "$len" "$OUT"
echo "$OUT: $(du -h "$OUT" | cut -f1)"
