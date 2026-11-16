#!/usr/bin/env bash
# モデルをダウンロードする。途中で止まっても再実行で続きから。
#   bash download_models.sh qwen     Qwen-Image-Edit-2511 一式 (約31GB / トークン不要 / Apache 2.0)
#   bash download_models.sh flux     FLUX 3 Image Klein 一式   (約24GB / 要HF_TOKEN / FLUX Kommunity License)
#   bash download_models.sh all
# FLUX は事前に https://huggingface.co/black-forest-labs/flux-3-image-klein-comfy でライセンスに同意し、
#   export HF_TOKEN=hf_xxx   を設定するか、起動ノートブックでトークンを登録してから実行する。
#   登録済みトークンは HF_TOKEN_PATH (既定 /notebooks/.hf/token) から読む。
set -euo pipefail
MODEL_DIR="${MODEL_DIR:-/tmp/models}"
WHAT="${1:-all}"

get() { # repo  repo内パス  保存先フォルダ
  local repo="$1" path="$2" dest="$MODEL_DIR/$3" name
  name="$(basename "$path")"
  mkdir -p "$dest"
  if [ -s "$dest/$name" ]; then echo "[skip] $name"; return; fi
  echo "[get ] $repo :: $path"
  local stage="$MODEL_DIR/.stage/$repo"
  hf download "$repo" "$path" --local-dir "$stage"
  mv "$stage/$path" "$dest/$name"
}

if [ "$WHAT" = "qwen" ] || [ "$WHAT" = "all" ]; then
  get Comfy-Org/Qwen-Image-Edit_ComfyUI      split_files/diffusion_models/qwen_image_edit_2511_fp8mixed.safetensors diffusion_models
  get Comfy-Org/HunyuanVideo_1.5_repackaged  split_files/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors        text_encoders
  get Comfy-Org/Qwen-Image_ComfyUI           split_files/vae/qwen_image_vae.safetensors                             vae
  get lightx2v/Qwen-Image-Edit-2511-Lightning Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors           loras
fi

if [ "$WHAT" = "flux" ] || [ "$WHAT" = "all" ]; then
  TP="${HF_TOKEN_PATH:-/notebooks/.hf/token}"
  if [ -z "${HF_TOKEN:-}" ] && [ -s "$TP" ]; then export HF_TOKEN="$(tr -d '[:space:]' < "$TP")"; fi
  if [ -z "${HF_TOKEN:-}" ]; then
    echo "[flux] HF_TOKEN が未設定のためスキップしました(起動ノートブックのセル2でトークンを登録してください)"; 
    [ "$WHAT" = "flux" ] && exit 1 || exit 0
  fi
  R=black-forest-labs/flux-3-image-klein-comfy
  get $R diffusion_models/flux3-image-klein-int8-convrot.safetensors              diffusion_models
  get $R diffusion_models/flux3-image-klein-base-int8-convrot.safetensors         diffusion_models
  get $R text_encoders/qwen3vl_4b_int8_convrot.safetensors                        text_encoders
  get $R text_encoders/qwen3.5_9b_flux3_prompt_upsampler_w4a8.safetensors         text_encoders
  get $R vae/flux2-vae.safetensors                                                vae
fi
rm -rf "$MODEL_DIR/.stage"
du -sh "$MODEL_DIR"/* 2>/dev/null || true
