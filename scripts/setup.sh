#!/usr/bin/env bash
# ComfyUI本体・カスタムノード・ワークフローを配置する。何度実行しても安全。
#   bash setup.sh
# 環境変数:
#   COMFY_DIR   ComfyUIの場所        (既定 /notebooks/ComfyUI  ※永続ストレージ)
#   MODEL_DIR   モデルの置き場所     (既定 /tmp/models         ※容量の大きい一時領域。マシン停止で消える)
#   INSTALL_SEETHROUGH=0 で See-through ノードを入れない
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMFY_DIR="${COMFY_DIR:-/notebooks/ComfyUI}"
MODEL_DIR="${MODEL_DIR:-/tmp/models}"

if [ ! -d "$COMFY_DIR/.git" ]; then
  git clone --depth 1 https://github.com/Comfy-Org/ComfyUI "$COMFY_DIR"
else
  git -C "$COMFY_DIR" pull --ff-only || echo "[setup] ComfyUIの更新をスキップ(ローカル変更あり)"
fi
pip install --no-cache-dir -r "$COMFY_DIR/requirements.txt"

if [ "${INSTALL_SEETHROUGH:-1}" = "1" ]; then
  N="$COMFY_DIR/custom_nodes/ComfyUI-See-through"
  [ -d "$N/.git" ] || git clone --depth 1 https://github.com/jtydhr88/ComfyUI-See-through "$N"
  # opencv-python はGUI版でlibGL依存が増えるため、headless版が入っていれば入れ直さない
  grep -v '^opencv-python' "$N/requirements.txt" | pip install --no-cache-dir -r /dev/stdin
  python -c "import cv2" 2>/dev/null || pip install --no-cache-dir opencv-python-headless
fi

mkdir -p "$MODEL_DIR"/{diffusion_models,text_encoders,vae,loras}
cat > "$COMFY_DIR/extra_model_paths.yaml" <<YAML
live2d_parts:
  base_path: $MODEL_DIR
  diffusion_models: diffusion_models
  text_encoders: text_encoders
  vae: vae
  loras: loras
YAML

W="$COMFY_DIR/user/default/workflows/live2d-parts"
mkdir -p "$W"
cp "$HERE"/workflows/live2d_*.json "$W"/
# 起動ノートブックを作業フォルダへ(設定を書き換えた既存ファイルは上書きしない)
if [ -d /notebooks ] && [ -f "$HERE/notebooks/Live2D_Parts_START.ipynb" ]; then cp -n "$HERE/notebooks/Live2D_Parts_START.ipynb" /notebooks/ || true; fi
echo "[setup] 完了: ComfyUI=$COMFY_DIR  モデル置き場=$MODEL_DIR  ワークフロー=$W"
