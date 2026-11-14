#!/bin/bash
# Video -> G1 motions with GVHMR + GMR and ViT-H (seeds 42, 1, 2), ready for BeyondMimic and SONIC.
# Run from the project folder: scripts/video_to_motion.sh <video.mp4> <name> [--static-camera]
# Video at 30 fps (GMR assumes it): ffmpeg -i in.mp4 -vf fps=30 -an video.mp4
set -e
VIDEO=$(realpath "$1"); NAME=$2; STATIC=$3
P=$(pwd); T=$P/third_party; OUT=$P/runs/videos2motion/$NAME
MJ=$T/mjlab/.venv/bin/python
SAM=third-party/Fast-SAM-3D-Body/checkpoints/sam-3d-body-dinov3
mkdir -p $OUT $P/data/motions/gmr $P/data/motions/vith $P/runs/sonic

gvhmr_flags=(); vith_flags=()
[ "$STATIC" = --static-camera ] && gvhmr_flags=(-s) && vith_flags=(--static-cam)

echo "GVHMR + GMR"
t0=$(date +%s)
(cd $T/GVHMR && .venv/bin/python tools/demo/demo.py --video=$VIDEO --output_root $OUT/gvhmr "${gvhmr_flags[@]}")
stem=$(basename $VIDEO .mp4)
(cd $T/GMR && xvfb-run -a .venv/bin/python scripts/gvhmr_to_robot.py --gvhmr_pred_file $OUT/gvhmr/$stem/hmr4d_results.pt \
  --robot unitree_g1 --save_path $OUT/gmr.pkl)
t1=$(date +%s)

echo "ViT-H"
for seed in 42 1 2; do
  (cd $T/vit-h && PYTHONPATH=$T/vit-h .venv/bin/python tools/infer_video.py --video $VIDEO --ckpt vith_offline_g1.ckpt \
    --sam3d-ckpt-path $SAM/model.ckpt --sam3d-mhr-path $SAM/assets/mhr_model.pt --sam3d-root third-party/Fast-SAM-3D-Body \
    --output-root $OUT/vith --output $OUT/vith_s$seed.npz --seed $seed "${vith_flags[@]}")
  (cd $P/scripts && $MJ vith_to_gmr.py $OUT/vith_s$seed.npz --output-file $OUT/vith_s$seed.pkl)
done

t2=$(date +%s)
echo "$NAME,gvhmr_gmr,video_to_g1,$((t1 - t0)),$(nvidia-smi --query-gpu=name --format=csv,noheader | head -1)" >> $OUT/timings.csv
echo "$NAME,vith,video_to_g1_3_seeds,$((t2 - t1)),$(nvidia-smi --query-gpu=name --format=csv,noheader | head -1)" >> $OUT/timings.csv

echo "converting"
cd $P/scripts
for m in gmr vith_s42 vith_s1 vith_s2; do
  src=${m%%_*}; suffix=${m#vith}; [ $m = vith_s42 ] && suffix=""; [ $src = gmr ] && suffix=""
  $MJ gmr_to_npz.py $OUT/$m.pkl --output-file $P/data/motions/$src/$NAME$suffix.npz
  $MJ gmr_to_sonic.py $OUT/$m.pkl --output-file $P/runs/sonic/${src}_$NAME${suffix}_in.npz
done
echo "done: data/motions/{gmr,vith}/$NAME*.npz (BeyondMimic), runs/sonic/*_${NAME}*_in.npz (SONIC)"
