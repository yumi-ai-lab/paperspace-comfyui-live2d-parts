#!/usr/bin/env bash
# ComfyUIを起動する。Paperspaceでは jupyter-server-proxy 経由で  <ノートブックURL>/proxy/8188/  から開く。
set -euo pipefail
COMFY_DIR="${COMFY_DIR:-/notebooks/ComfyUI}"
cd "$COMFY_DIR"
exec python main.py --listen 0.0.0.0 --port "${COMFY_PORT:-8188}" \
  --extra-model-paths-config "$COMFY_DIR/extra_model_paths.yaml" "$@"
