#!/usr/bin/env bash
# Installs the tools in third_party/, their environments and the checkpoints that need no sign-up.
# See the README's Install section. Safe to run again: finished steps are skipped.
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: bash install.sh [--cuda cu130|cu126] [--only <part>]... [--harness-from <path>]

Parts, in the order they run:
  tools   clone the tools into third_party/ at the pinned commits, apply patches/
  gvhmr   GVHMR's environment (with pytorch3d built from source) and its checkpoints
  gmr     GMR's environment (uv sync)
  vith    ViT-H's environment (with Fast-SAM-3D-Body's packages and pytorch3d) and its checkpoints
  mjlab   mjlab's environment (uv sync --extra <cuda>), plus rosbags, mcap and the harness's requirements
  sonic   SONIC v1.1 (nvidia/GEAR-SONIC, revision 6733128a)
  checks  list the manual steps that are still missing (SMPL, SMPL-X, SAM 3D Body, ROS 2, AIST++)

Options:
  --cuda cu130|cu126    PyTorch build. Default: from nvidia-smi. Compute capability 10.0 or newer
                        (Blackwell) -> cu130 (driver 580 or newer); older GPUs -> cu126 (driver 525 or newer)
  --only <part>         run only this part; can be given more than once
  --harness-from <path> clone g1-eval-harness from this path or URL instead of GitHub
  -h, --help            show this help

Needs: git, uv, hf (uv tool install huggingface_hub), gcc and g++ (build-essential), an NVIDIA driver.
Set MAX_JOBS to change the number of parallel compile jobs for pytorch3d (default 8).
EOF
}

ROOT=$(cd "$(dirname "$0")" && pwd)
TP=$ROOT/third_party
TORCH=2.14.0
TORCHVISION=0.29.1
ULTRALYTICS=8.4.212
HARNESS_URL=https://github.com/amirkhonaripov/g1-eval-harness.git

CUDA=""
PARTS=""
HARNESS_FROM=""
while [ $# -gt 0 ]; do
  case $1 in
    --cuda) CUDA=$2; shift 2 ;;
    --only) PARTS="$PARTS $2"; shift 2 ;;
    --harness-from) HARNESS_FROM=$2; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown argument: $1"; usage; exit 1 ;;
  esac
done
if [ -z "$PARTS" ]; then
  PARTS="tools gvhmr gmr vith mjlab sonic checks"
fi
for part in $PARTS; do
  case $part in
    tools|gvhmr|gmr|vith|mjlab|sonic|checks) ;;
    *) echo "unknown part: $part (parts: tools gvhmr gmr vith mjlab sonic checks)"; exit 1 ;;
  esac
done
case $CUDA in
  ""|cu130|cu126) ;;
  *) echo "--cuda must be cu130 or cu126"; exit 1 ;;
esac

# print a command, then run it
run() {
  echo "+ $*"
  "$@"
}

say() {
  echo
  echo "=== $*"
}

need() {
  if ! command -v "$1" > /dev/null; then
    echo "missing: $1. $2"
    exit 1
  fi
}

need git "sudo apt install git"
need uv "curl -LsSf https://astral.sh/uv/install.sh | sh"

# ---------- PyTorch build ----------

PT_INDEX=""
ARCH_LIST=""

pick_cuda() {
  if [ -n "$PT_INDEX" ]; then
    return
  fi
  need nvidia-smi "Install the NVIDIA driver first."
  local line cc driver cc_major driver_major
  line=$(nvidia-smi --query-gpu=compute_cap,driver_version --format=csv,noheader | head -n 1)
  cc=${line%%,*}
  driver=${line##*, }
  cc_major=${cc%%.*}
  driver_major=${driver%%.*}
  ARCH_LIST=$(nvidia-smi --query-gpu=compute_cap --format=csv,noheader | sort -u | paste -sd ';')
  echo "GPU compute capability $cc, driver $driver"
  if [ -z "$CUDA" ]; then
    if [ "$cc_major" -ge 10 ]; then
      CUDA=cu130
    else
      CUDA=cu126
    fi
    echo "PyTorch build: $CUDA (detected; override with --cuda)"
  else
    echo "PyTorch build: $CUDA (from --cuda)"
  fi
  # minimum drivers: NVIDIA's CUDA minor version compatibility table (13.x: 580, 12.x: 525)
  if [ "$CUDA" = cu130 ] && [ "$driver_major" -lt 580 ]; then
    echo "Driver $driver is too old for CUDA 13.0 (cu130): it needs 580 or newer. Update the NVIDIA driver."
    exit 1
  fi
  if [ "$CUDA" = cu126 ] && [ "$driver_major" -lt 525 ]; then
    echo "Driver $driver is too old for CUDA 12.6 (cu126): it needs 525 or newer. Update the NVIDIA driver."
    exit 1
  fi
  if [ "$CUDA" = cu126 ] && [ "$cc_major" -ge 10 ]; then
    echo "This GPU (compute capability $cc) needs CUDA 12.8 or newer; use cu130."
    exit 1
  fi
  if [ "$CUDA" = cu130 ] && [ "${cc/./}" -lt 75 ]; then
    echo "CUDA 13 doesn't support compute capability $cc (older than 7.5); use cu126."
    exit 1
  fi
  PT_INDEX=https://download.pytorch.org/whl/$CUDA
}

# ---------- helpers ----------

# clone a repo into a folder at a commit; skip if it is already there
clone_at() {
  local dir=$1 url=$2 commit=$3 head
  if [ -d "$dir/.git" ]; then
    head=$(git -C "$dir" rev-parse HEAD)
    if [[ $head == $commit* ]]; then
      echo "$dir: already at $commit"
      return
    fi
    echo "$dir is at ${head:0:7}, not $commit. Check out $commit there, or move the folder away, and run again."
    exit 1
  fi
  run git clone "$url" "$dir"
  run git -C "$dir" checkout -q "$commit"
}

apply_patch() {
  local dir=$1 patch=$2
  if git -C "$dir" apply --reverse --check "$patch" 2> /dev/null; then
    echo "$patch: already applied"
  else
    run git -C "$dir" apply "$patch"
  fi
}

# hf download of one file of ViT-H's checkpoint dataset into a folder, or a copy from the other tool
vith_ckpt() {
  local dest=$1 file=$2 other
  if [ -s "$dest/$file" ]; then
    echo "$dest/$file: already there"
    return
  fi
  for other in "$TP/GVHMR" "$TP/vit-h"; do
    if [ -s "$other/$file" ]; then
      run mkdir -p "$(dirname "$dest/$file")"
      run cp "$other/$file" "$dest/$file"
      return
    fi
  done
  need hf "uv tool install huggingface_hub"
  run hf download eerrr1/ViT-H-checkpoints "$file" --repo-type dataset --local-dir "$dest"
}

# the chumpy package fails on Python 3.12 and numpy 1.26 without these two fixes
fix_chumpy() {
  local python=$1 ch
  ch=$("$python" -c "import importlib.util, os; print(os.path.dirname(importlib.util.find_spec('chumpy').origin))")
  run sed -i "s/inspect.getargspec/inspect.getfullargspec/" "$ch/ch.py"
  run sed -i "s/^from numpy import bool, int, float, complex, object, unicode, str, nan, inf/from numpy import nan, inf/" \
    "$ch/__init__.py"
}

# torch with CUDA, the tool's requirements without the ones we replace, then pytorch3d and the tool itself
make_torch_env() {
  local dir=$1
  run uv venv --allow-existing --managed-python -p 3.12 "$dir/.venv"
  run uv pip install --python "$dir/.venv/bin/python" --index-url "$PT_INDEX" \
    torch==$TORCH torchvision==$TORCHVISION
}

pytorch3d_wheel() {
  ls "$TP/pytorch3d/dist-$CUDA"/pytorch3d-*.whl
}

# pytorch3d 0.7.9 (commit 3eac7c6 of its main branch, as built here) for our torch, built once
build_pytorch3d() {
  local venv sp nvcc cuda_home
  if pytorch3d_wheel > /dev/null 2>&1; then
    echo "pytorch3d wheel for $CUDA: already built"
    return
  fi
  need g++ "sudo apt install build-essential"
  clone_at "$TP/pytorch3d" https://github.com/facebookresearch/pytorch3d.git 3eac7c6
  # torch 2.14's headers need C++20
  if grep -q -- "-std=c++17" "$TP/pytorch3d/setup.py"; then
    run sed -i "s/-std=c++17/-std=c++20/" "$TP/pytorch3d/setup.py"
  fi
  # a build environment with the same torch and the matching CUDA compiler from pip
  venv=$TP/pytorch3d/.venv-$CUDA
  run uv venv --allow-existing --managed-python -p 3.12 "$venv"
  run uv pip install --python "$venv/bin/python" --extra-index-url "$PT_INDEX" \
    torch==$TORCH "cuda-toolkit[nvcc,cccl]" setuptools wheel ninja pip
  sp=$("$venv/bin/python" -c "import sysconfig; print(sysconfig.get_paths()['purelib'])")
  nvcc=$(ls "$sp"/nvidia/*/bin/nvcc | head -n 1)
  cuda_home=$(dirname "$(dirname "$nvcc")")
  # pip's CUDA runtime has only libcudart.so.<major>; the linker wants libcudart.so
  run mkdir -p "$venv/link"
  run ln -sf "$(ls "$sp"/nvidia/*/lib/libcudart.so.* | head -n 1)" "$venv/link/libcudart.so"
  run env CUDA_HOME="$cuda_home" PATH="$cuda_home/bin:$venv/bin:$PATH" \
    CPATH="$(ls -d "$sp"/nvidia/*/include | paste -sd ':')" \
    LIBRARY_PATH="$venv/link:$(ls -d "$sp"/nvidia/*/lib | paste -sd ':')" \
    FORCE_CUDA=1 TORCH_CUDA_ARCH_LIST="$ARCH_LIST" MAX_JOBS="${MAX_JOBS:-8}" \
    "$venv/bin/python" -m pip wheel --no-build-isolation --no-deps "$TP/pytorch3d" -w "$TP/pytorch3d/dist-$CUDA"
}

# ---------- parts ----------

part_tools() {
  run mkdir -p "$TP"
  clone_at "$TP/GVHMR" https://github.com/zju3dv/GVHMR.git ee960bb
  clone_at "$TP/GMR" https://github.com/YanjieZe/GMR.git 25f56db
  clone_at "$TP/vit-h" https://github.com/mileret/ViT-H-release.git 2482c5c
  clone_at "$TP/vit-h/third-party/Fast-SAM-3D-Body" https://github.com/yangtiming/Fast-SAM-3D-Body.git d72aa36
  clone_at "$TP/mjlab" https://github.com/mujocolab/mjlab.git 1b5c91c
  clone_at "$TP/GR00T-WholeBodyControl" https://github.com/NVlabs/GR00T-WholeBodyControl.git 1e1ec4f
  clone_at "$TP/g1-eval-harness" "${HARNESS_FROM:-$HARNESS_URL}" 2b3f676
  if [ -n "$HARNESS_FROM" ]; then
    run git -C "$TP/g1-eval-harness" remote set-url origin "$HARNESS_URL"
  fi
  apply_patch "$TP/GVHMR" "$ROOT/patches/gvhmr.patch"
  apply_patch "$TP/vit-h" "$ROOT/patches/vith.patch"
}

part_gvhmr() {
  local dir=$TP/GVHMR py=$TP/GVHMR/.venv/bin/python req
  if [ -x "$py" ] && "$py" -c "import torch, pytorch3d, hmr4d, chumpy, yacs" 2> /dev/null; then
    echo "GVHMR environment: already done"
  else
    pick_cuda
    build_pytorch3d
    make_torch_env "$dir"
    req=$(mktemp)
    grep -v -E '^(--extra-index-url|torch|torchvision|numpy|pytorch3d|ultralytics)' "$dir/requirements.txt" > "$req"
    run uv pip install --python "$py" pip setuptools wheel
    run uv pip install --python "$py" --no-build-isolation-package chumpy -r "$req" "numpy<2" ultralytics==$ULTRALYTICS yacs
    rm "$req"
    run uv pip install --python "$py" "$(pytorch3d_wheel)"
    run uv pip install --python "$py" --no-deps -e "$dir"
    fix_chumpy "$py"
    run "$py" -c "import torch, pytorch3d, hmr4d, chumpy, yacs; from pytorch3d.transforms import quaternion_to_matrix; \
print('GVHMR OK', torch.__version__, torch.cuda.get_device_name(0), quaternion_to_matrix(torch.eye(4)[:1].cuda()).shape)"
  fi
  # checkpoints: GVHMR's own from its Google Drive folder, the rest are the same files as ViT-H's
  if [ -s "$dir/inputs/checkpoints/gvhmr/gvhmr_siga24_release.ckpt" ]; then
    echo "GVHMR checkpoint: already there"
  else
    run mkdir -p "$dir/inputs/checkpoints/gvhmr"
    if ! run uvx gdown 1c9iCeKFN4Kr6cMPJ9Ss6Jdc3SZFnO5NP -O "$dir/inputs/checkpoints/gvhmr/gvhmr_siga24_release.ckpt"; then
      echo "Google Drive refused the download (often a quota); try again later. 'checks' lists it."
    fi
  fi
  vith_ckpt "$dir" inputs/checkpoints/hmr2/epoch=10-step=25000.ckpt
  vith_ckpt "$dir" inputs/checkpoints/vitpose/vitpose-h-multi-coco.pth
  vith_ckpt "$dir" inputs/checkpoints/yolo/yolov8x.pt
  vith_ckpt "$dir" inputs/checkpoints/dpvo/dpvo.pth
}

part_gmr() {
  local py=$TP/GMR/.venv/bin/python
  if [ -x "$py" ] && "$py" -c "import general_motion_retargeting, smplx" 2> /dev/null; then
    echo "GMR environment: already done"
    return
  fi
  run uv sync --project "$TP/GMR"
}

part_vith() {
  local dir=$TP/vit-h py=$TP/vit-h/.venv/bin/python req
  if [ -x "$py" ] && "$py" -c "import torch, pytorch3d, hmr4d, chumpy, mhr, braceexpand, easydict" 2> /dev/null; then
    echo "ViT-H environment: already done"
  else
    pick_cuda
    build_pytorch3d
    make_torch_env "$dir"
    req=$(mktemp)
    grep -v -E '^(--extra-index-url|torch|torchvision|numpy|pytorch3d|ultralytics|jupyter|ipdb|black)' \
      "$dir/requirements.txt" > "$req"
    run uv pip install --python "$py" pip setuptools wheel cython
    # mhr and the small packages are what Fast-SAM-3D-Body needs
    run uv pip install --python "$py" --no-build-isolation-package chumpy --no-build-isolation-package cython_bbox \
      -r "$req" "numpy<2" ultralytics==$ULTRALYTICS mhr pytorch-lightning yacs roma omegaconf huggingface_hub \
      braceexpand easydict
    rm "$req"
    run uv pip install --python "$py" "$(pytorch3d_wheel)"
    run uv pip install --python "$py" --no-deps -e "$dir"
    fix_chumpy "$py"
    run "$py" -c "import torch, pytorch3d, hmr4d, chumpy, mhr, braceexpand, easydict; print('ViT-H OK', torch.__version__, torch.cuda.get_device_name(0))"
  fi
  vith_ckpt "$dir" vith_offline_g1.ckpt
  vith_ckpt "$dir" inputs/checkpoints/hmr2/epoch=10-step=25000.ckpt
  vith_ckpt "$dir" inputs/checkpoints/vitpose/vitpose-h-multi-coco.pth
  vith_ckpt "$dir" inputs/checkpoints/yolo/yolov8x.pt
  if [ -s "$dir/inputs/checkpoints/g1_tracker/model_step_020000_g1.onnx" ]; then
    echo "g1_tracker checkpoint: already there"
  else
    need hf "uv tool install huggingface_hub"
    run hf download eerrr1/ViT-H-checkpoints model_step_020000_g1.onnx --repo-type dataset \
      --local-dir "$dir/inputs/checkpoints/g1_tracker"
  fi
}

part_mjlab() {
  local py=$TP/mjlab/.venv/bin/python
  if [ -x "$py" ] && "$py" -c "import mjlab, torch, rosbags, mcap, yaml, cv2, imageio, pytest" 2> /dev/null; then
    echo "mjlab environment: already done"
    return
  fi
  pick_cuda
  run uv sync --project "$TP/mjlab" --extra "$CUDA"
  run uv pip install --python "$py" rosbags mcap -r "$TP/g1-eval-harness/requirements.txt"
}

part_sonic() {
  local dir=$TP/GR00T-WholeBodyControl/gear_sonic_deploy/policy
  if [ -s "$dir/sonic_v1_1/model_encoder.onnx" ] && [ -s "$dir/sonic_v1_1/model_decoder.onnx" ]; then
    echo "SONIC v1.1: already there"
    return
  fi
  need hf "uv tool install huggingface_hub"
  run hf download nvidia/GEAR-SONIC sonic_v1_1/model_encoder.onnx sonic_v1_1/model_decoder.onnx \
    sonic_v1_1/observation_config.yaml --revision 6733128a --local-dir "$dir"
}

MISSING=0

# report a manual item: what it is, README section, then the paths it needs
check() {
  local what=$1 section=$2 path missing=0 first=""
  shift 2
  for path in "$@"; do
    if [ ! -e "$path" ]; then
      missing=$((missing + 1))
      first=${first:-$path}
    fi
  done
  if [ "$missing" -eq 0 ]; then
    echo "  [ok]      $what"
  else
    echo "  [missing] $what"
    echo "            $missing of $# missing, e.g. ${first#"$ROOT"/}"
    echo "            see README: $section"
    MISSING=$((MISSING + 1))
  fi
}

part_checks() {
  local by_hand="Install > What you do by hand" ros="Install > ROS 2 Jazzy and the ROS 2 stack" g s
  local smpl=()
  for g in NEUTRAL MALE FEMALE; do
    smpl+=("$TP/GVHMR/inputs/checkpoints/body_models/smpl/SMPL_$g.pkl")
    smpl+=("$TP/GVHMR/inputs/checkpoints/body_models/smplx/SMPLX_$g.npz")
    smpl+=("$TP/GMR/assets/body_models/smplx/SMPLX_$g.pkl")
    smpl+=("$TP/vit-h/inputs/checkpoints/body_models/smpl/SMPL_$g.pkl")
    smpl+=("$TP/vit-h/inputs/checkpoints/body_models/smplx/SMPLX_$g.npz")
  done
  s=$TP/vit-h/third-party/Fast-SAM-3D-Body/checkpoints/sam-3d-body-dinov3
  echo "Manual steps:"
  check "SMPL and SMPL-X body models (sign-up)" "$by_hand" "${smpl[@]}"
  check "SAM 3D Body for ViT-H (gated, hf auth login)" "$by_hand" "$s/model.ckpt" "$s/assets/mhr_model.pt"
  check "GVHMR checkpoint from Google Drive (if it refused: bash install.sh --only gvhmr, later)" \
    "Install > What install.sh does" "$TP/GVHMR/inputs/checkpoints/gvhmr/gvhmr_siga24_release.ckpt"
  check "ROS 2 Jazzy (BeyondMimic route only)" "$ros" /opt/ros/jazzy/setup.bash
  check "the ROS 2 stack in ~/colcon_ws (BeyondMimic route only)" "$ros" \
    "$HOME/colcon_ws/install/motion_tracking_controller"
  check "AIST++ annotations (optional: accuracy of Pop and Jazz)" "Run > 1c" "$ROOT/data/aistpp/motions"
  if [ "$MISSING" -eq 0 ]; then
    echo "Everything is in place."
  else
    echo "$MISSING manual item(s) missing."
  fi
}

for part in tools gvhmr gmr vith mjlab sonic checks; do
  case " $PARTS " in
    *" $part "*) ;;
    *) continue ;;
  esac
  say "$part"
  start=$SECONDS
  "part_$part"
  echo "=== $part: $((SECONDS - start)) s"
done
