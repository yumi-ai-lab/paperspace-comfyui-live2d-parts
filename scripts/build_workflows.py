#!/usr/bin/env python3
"""Live2Dパーツ補完用ワークフロー(ComfyUI API形式)を生成する。

    python scripts/build_workflows.py

出力: workflows/*.json  (ComfyUIの画面にドラッグ&ドロップでも開ける)

共通の考え方:
  1. 元画像とマスク画像(白=描き直す範囲)を読み込む
  2. マスク範囲だけをモデルに再生成させる(潜在ノイズマスク)
  3. 生成結果を元の解像度に戻し、マスク範囲だけ元画像へ貼り戻す
     → マスクの外は元ピクセルが1bitも変わらない
  4. 元画像のアルファを保持し、描き足した範囲だけ不透明にして保存
"""
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "workflows"

DEFAULT_PROMPT = (
    "Remove the front hair that covers the face and paint the hidden forehead, "
    "eyebrows and face outline underneath, in the same anime art style, line weight "
    "and skin colour. Keep everything else unchanged."
)


def node(class_type, title, **inputs):
    return {"class_type": class_type, "_meta": {"title": title}, "inputs": inputs}


def common_pre(grow, blur):
    """入力・マスク整形・透明部分の白埋め。"""
    return {
        "1": node("LoadImage", "元画像 (RGBA可)", image="live2d_test_image.png"),
        "2": node("LoadImage", "マスク画像 (白=描き直す範囲)", image="live2d_test_mask.png"),
        "3": node("ImageToMask", "マスク画像→マスク", image=["2", 0], channel="red"),
        "4": node("GrowMask", "マスクを広げる", mask=["3", 0], expand=grow, tapered_corners=True),
        "5": node("MaskToImage", "ぼかし用に画像化", mask=["4", 0]),
        "6": node("ImageBlur", "境界をぼかす", image=["5", 0], blur_radius=blur, sigma=max(0.1, blur / 2)),
        "7": node("ImageToMask", "合成用ソフトマスク", image=["6", 0], channel="red"),
        "8": node("EmptyImage", "白背景", width=64, height=64, batch_size=1, color=16777215),
        "9": node("ImageCompositeMasked", "透明部分を白で埋める(モデル入力用)",
                  destination=["1", 0], source=["8", 0], x=0, y=0, resize_source=True, mask=["1", 1]),
        "10": node("GetImageSize", "元画像サイズ", image=["1", 0]),
    }


def common_post(decoded, prefix):
    """元解像度へ戻す → マスク範囲だけ貼り戻す → アルファ復元 → 保存。"""
    return {
        "80": node("ImageScale", "元の解像度へ戻す", image=decoded, upscale_method="lanczos",
                   width=["10", 0], height=["10", 1], crop="disabled"),
        "81": node("ImageCompositeMasked", "マスク範囲だけ元画像へ貼り戻す",
                   destination=["1", 0], source=["80", 0], x=0, y=0, resize_source=False, mask=["7", 0]),
        "82": node("MaskComposite", "透明のまま残す範囲 = 元の透明 − 描き足し範囲",
                   destination=["1", 1], source=["4", 0], x=0, y=0, operation="subtract"),
        "83": node("JoinImageWithAlpha", "アルファを付け直す", image=["81", 0], alpha=["82", 0]),
        "90": node("SaveImage", "保存: 完成パーツ(RGBA)", images=["83", 0], filename_prefix=f"live2d_parts/{prefix}_final"),
        "91": node("SaveImage", "保存: モデルの生出力(確認用)", images=["80", 0], filename_prefix=f"live2d_parts/{prefix}_raw"),
    }


def qwen(fast, grow=12, blur=8):
    """Qwen-Image-Edit-2511。fast=True で 4ステップLoRA。"""
    wf = common_pre(grow, blur)
    wf.update({
        "20": node("UNETLoader", "Qwen-Image-Edit-2511", unet_name="qwen_image_edit_2511_fp8mixed.safetensors", weight_dtype="default"),
        "21": node("CLIPLoader", "テキストエンコーダ", clip_name="qwen_2.5_vl_7b_fp8_scaled.safetensors", type="qwen_image", device="default"),
        "22": node("VAELoader", "VAE", vae_name="qwen_image_vae.safetensors"),
        "23": node("ModelSamplingAuraFlow", "shift", model=["20", 0], shift=3.1),
        "24": node("CFGNorm", "CFGNorm", model=["23", 0], strength=1.0),
        "26": node("FluxKontextImageScale", "モデル用に約1MPへ", image=["9", 0]),
        "27": node("TextEncodeQwenImageEditPlus", "指示文 (ここを書き換える)",
                   clip=["21", 0], vae=["22", 0], image1=["26", 0], prompt=DEFAULT_PROMPT),
        "28": node("TextEncodeQwenImageEditPlus", "ネガティブ", clip=["21", 0], vae=["22", 0], image1=["26", 0], prompt=""),
        "29": node("FluxKontextMultiReferenceLatentMethod", "参照方式(+)", conditioning=["27", 0], reference_latents_method="index_timestep_zero"),
        "30": node("FluxKontextMultiReferenceLatentMethod", "参照方式(-)", conditioning=["28", 0], reference_latents_method="index_timestep_zero"),
        "31": node("VAEEncode", "元画像を潜在へ", pixels=["26", 0], vae=["22", 0]),
        "32": node("SetLatentNoiseMask", "マスク範囲だけ再生成", samples=["31", 0], mask=["4", 0]),
    })
    model = ["24", 0]
    steps, cfg = 40, 4.0
    if fast:
        wf["25"] = node("LoraLoaderModelOnly", "4ステップLoRA", model=["24", 0],
                        lora_name="Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors", strength_model=1.0)
        model = ["25", 0]
        steps, cfg = 4, 1.0
    wf.update({
        "33": node("KSampler", "サンプラー", model=model, seed=20261115, steps=steps, cfg=cfg,
                   sampler_name="euler", scheduler="simple", positive=["29", 0], negative=["30", 0],
                   latent_image=["32", 0], denoise=1.0),
        "34": node("VAEDecode", "デコード", samples=["33", 0], vae=["22", 0]),
    })
    wf.update(common_post(["34", 0], "qwen_fast" if fast else "qwen_quality"))
    return wf


def flux3(distilled, upsampler=True, grow=12, blur=8):
    """FLUX 3 Image Klein。distilled=True で16ステップ版。"""
    system_prompt = (OUT / "flux3_upsampler_system_prompt.txt").read_text(encoding="utf-8")
    wf = common_pre(grow, blur)
    unet = "flux3-image-klein-int8-convrot.safetensors" if distilled else "flux3-image-klein-base-int8-convrot.safetensors"
    wf.update({
        "50": node("UNETLoader", "FLUX 3 Image Klein", unet_name=unet, weight_dtype="default"),
        "51": node("CLIPLoader", "テキストエンコーダ", clip_name="qwen3vl_4b_int8_convrot.safetensors", type="flux3", device="default"),
        "52": node("VAELoader", "VAE", vae_name="flux2-vae.safetensors"),
        "53": node("ImageScaleToTotalPixels", "モデル用に約1MPへ", image=["9", 0], upscale_method="lanczos",
                   megapixels=1.0, resolution_steps=16),
        "70": node("PrimitiveStringMultiline", "指示文 (ここを書き換える)", value=DEFAULT_PROMPT),
    })
    text = ["70", 0]
    if upsampler:
        wf.update({
            "54": node("CLIPLoader", "プロンプト拡張モデル", clip_name="qwen3.5_9b_flux3_prompt_upsampler_w4a8.safetensors", type="flux3", device="default"),
            "55": node("PrimitiveStringMultiline", "拡張用システムプロンプト(公式テンプレートのまま)", value=system_prompt),
            "56": node("TextGenerate", "短い指示を詳しい指示へ拡張", **{
                "clip": ["54", 0], "prompt": ["70", 0], "max_length": 3584, "image": ["53", 0],
                "sampling_mode": "on", "sampling_mode.temperature": 1.0, "sampling_mode.top_k": 1,
                "sampling_mode.top_p": 0.95, "sampling_mode.min_p": 0.0,
                "sampling_mode.repetition_penalty": 1.05, "sampling_mode.seed": 0,
                "sampling_mode.presence_penalty": 0.0,
                "thinking": False, "use_default_template": True, "mtp": "off",
                "system_prompt": ["55", 0],
            }),
        })
        text = ["56", 0]
    steps, cfg = (16, 1.0) if distilled else (50, 3.5)
    wf.update({
        "57": node("CLIPTextEncode", "指示文エンコード", clip=["51", 0], text=text),
        "58": node("ConditioningZeroOut", "ネガティブ(ゼロ)", conditioning=["57", 0]),
        "59": node("ReferenceMultiLatent", "参照画像をセット", **{
            "positive": ["57", 0], "negative": ["58", 0], "vae": ["52", 0],
            "resolution": "keep resolution", "images.image0": ["53", 0],
        }),
        "60": node("VAEEncode", "元画像を潜在へ", pixels=["53", 0], vae=["52", 0]),
        "61": node("SetLatentNoiseMask", "マスク範囲だけ再生成", samples=["60", 0], mask=["4", 0]),
        "62": node("KSampler", "サンプラー", model=["50", 0], seed=20261115, steps=steps, cfg=cfg,
                   sampler_name="euler", scheduler="simple", positive=["59", 0], negative=["59", 1],
                   latent_image=["61", 0], denoise=1.0),
        "63": node("VAEDecode", "デコード", samples=["62", 0], vae=["52", 0]),
    })
    wf.update(common_post(["63", 0], "flux3_distilled" if distilled else "flux3_base"))
    return wf


def composite_only():
    """モデルを使わない合成部分だけの検証用(GPU不要)。"生成結果"の代わりに別画像を貼る。"""
    wf = common_pre(12, 8)
    wf["79"] = node("LoadImage", "生成結果の代役", image="live2d_test_standin.png")
    wf.update(common_post(["79", 0], "composite_only"))
    return wf


def main():
    files = {
        "live2d_inpaint_qwen2511_fast.json": qwen(fast=True),
        "live2d_inpaint_qwen2511_quality.json": qwen(fast=False),
        "live2d_inpaint_flux3klein_distilled.json": flux3(distilled=True),
        "live2d_inpaint_flux3klein_base.json": flux3(distilled=False),
        "live2d_inpaint_flux3klein_distilled_noupsampler.json": flux3(distilled=True, upsampler=False),
        "_selftest_composite_only.json": composite_only(),
    }
    for name, wf in files.items():
        (OUT / name).write_text(json.dumps(wf, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"wrote workflows/{name} ({len(wf)} nodes)")


if __name__ == "__main__":
    main()
