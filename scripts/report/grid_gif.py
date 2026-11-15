"""Labelled grid GIF of videos, with a metric line and timed failure and fall tags per cell."""

import argparse
import json
import subprocess
from pathlib import Path

BACKGROUND = "0x1e2a36"
BOX = "box=1:boxcolor=black@0.55"


def parse_args():
  parser = argparse.ArgumentParser(description="Labelled grid GIF of videos")
  parser.add_argument("out", help="output .gif")
  parser.add_argument("cols", type=int, help="cells per row")
  parser.add_argument("cells", help="JSON list of cells {label, metric, fail_s, fell_s, src}, row by row; src is a "
                      "video or \"blank\" (text only); from fail_s (s, the video's clock) on, a red \"tracking failure "
                      "at\" tag, from fell_s a dark red \"fell at\" tag above it")
  parser.add_argument("--duration", type=float, default=2.6, help="seconds; shorter videos hold their last frame")
  parser.add_argument("--fps", type=int, default=12)
  parser.add_argument("--cell", default="360x240", help="cell size WxH")
  return parser.parse_args()


def font(name):
  return subprocess.run(["fc-match", "-f", "%{file}", name], capture_output=True, text=True, check=True).stdout


def text(s):
  return s.replace(":", "\\:").replace("'", "’")


def tag(fontfile, label, t, y, color):
  return (f",drawtext=fontfile={fontfile}:text='{label} {t:.2f} s':x=6:y=h-{y}:fontsize=14:fontcolor=white:"
          f"box=1:boxcolor={color}:enable='gte(t\\,{t})'")


def main():
  args = parse_args()
  cells = json.loads(Path(args.cells).read_text())
  regular, bold = font("DejaVuSans"), font("DejaVuSans:bold")
  w, h = map(int, args.cell.split("x"))
  inputs, chains, layout = [], [], []
  for n, cell in enumerate(cells):
    if cell["src"] == "blank":
      inputs += ["-f", "lavfi", "-t", "1", "-i", f"color=c={BACKGROUND}:s={w}x{h}:r={args.fps}"]
    else:
      inputs += ["-i", cell["src"]]
    chain = (f"[{n}:v]fps={args.fps},scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:"
             f"(oh-ih)/2:color={BACKGROUND},tpad=stop_mode=clone:stop_duration={args.duration + 1}")
    chain += f",drawtext=fontfile={regular}:text='{text(cell['label'])}':x=6:y=6:fontsize=14:fontcolor=white:{BOX}"
    if cell.get("metric"):
      chain += f",drawtext=fontfile={regular}:text='{text(cell['metric'])}':x=6:y=26:fontsize=13:fontcolor=white:{BOX}"
    if cell.get("fail_s") is not None:
      chain += tag(bold, "tracking failure at", cell["fail_s"], 24, "0xc0392b@0.9")
    if cell.get("fell_s") is not None:
      chain += tag(bold, "fell at", cell["fell_s"], 24 if cell.get("fail_s") is None else 46, "0x7b241c@0.95")
    chains.append(f"{chain}[v{n}]")
    layout.append(f"{n % args.cols * w}_{n // args.cols * h}")
  stack = "".join(f"[v{n}]" for n in range(len(cells)))
  join = f"xstack=inputs={len(cells)}:layout={'|'.join(layout)}" if len(cells) > 1 else "null"
  graph = (";".join(chains) + f";{stack}{join},split[a][b];[a]palettegen=max_colors=64:stats_mode=diff[p];"
           "[b][p]paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle")
  subprocess.run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", graph, "-t", str(args.duration), args.out],
                 check=True)
  print(args.out)


if __name__ == "__main__":
  main()
