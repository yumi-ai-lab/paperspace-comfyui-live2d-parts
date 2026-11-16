# paperspace-comfyui-live2d-parts

`yumi-ai-lab/paperspace-comfyui`(基本版)を発展させた、**Live2Dパーツの補完・修正用** ComfyUI 環境。
1枚絵から切り出したパーツの「隠れて見えない部分」を、元の絵を壊さずに描き足す。

## 何が入っているか

| 場所 | 内容 |
|---|---|
| `Dockerfile` / `requirements.txt` | 基本版 + See-through用依存 + モデル取得ツール。モデル本体は同梱しない |
| `scripts/setup.sh` | ComfyUI本体、ComfyUI-See-through、ワークフローを配置 |
| `scripts/download_models.sh` | `qwen` / `flux` / `all` を指定してモデル取得 |
| `scripts/start.sh` | ComfyUI起動(8188) |
| `scripts/run_test.py` | ワークフローをAPIで実行し、結果を機械検証 |
| `scripts/build_workflows.py` | ワークフローJSONの生成元(設定を変えたらここを直して再生成) |
| `workflows/` | 補完ワークフロー5本(API形式。ComfyUI画面へドラッグ&ドロップで開ける) |

## ワークフロー

| ファイル | モデル | ステップ | 用途 |
|---|---|---|---|
| `live2d_inpaint_qwen2511_fast.json` | Qwen-Image-Edit-2511 + 4step LoRA | 4 | 試行錯誤用 |
| `live2d_inpaint_qwen2511_quality.json` | Qwen-Image-Edit-2511 | 40 | 仕上げ用 |
| `live2d_inpaint_flux3klein_distilled.json` | FLUX 3 Image Klein (distilled) | 16 | 短い指示を自動で詳細化して実行 |
| `live2d_inpaint_flux3klein_base.json` | FLUX 3 Image Klein (base) | 50 | 仕上げ用 |
| `live2d_inpaint_flux3klein_distilled_noupsampler.json` | 同上(プロンプト拡張なし) | 16 | 自分で詳しい英文を書く場合 |

入力は2枚: **元画像**(RGBA可)と**マスク画像**(白=描き直す範囲)。
出力 `*_final` は、マスクの外が元画像と完全一致し、描き足した範囲だけ不透明になったRGBA。
`*_raw` はモデルの生出力(確認用)。

仕組み: マスク範囲だけ潜在ノイズマスクで再生成 → 元解像度へ戻す → マスク範囲だけ元画像に貼り戻す → アルファ復元。

## 使い方(Paperspace)

マシンを起動するたびに、`/notebooks/Live2D_Parts_START.ipynb` を開いて上から順に実行する(Run All でも可)。

1. 設定(使うモデル、モデルを保存領域に残すか)
2. Hugging Faceトークンの登録(FLUXを使う場合、**初回だけ**。`/notebooks/.hf/token` に保存され、次回から入力不要)
3. ComfyUIと部品の準備
4. モデルの取得
5. ComfyUIの起動(セルを実行したままにする)

初回でノートブックがまだ無い場合は、ターミナルで次を実行すると配置される。

```bash
cp /opt/live2d-parts/notebooks/Live2D_Parts_START.ipynb /notebooks/
```

モデルは既定で `/tmp/models`(一時領域)に置く。マシンを止めると消えるが、ノートブックを実行し直せば戻る。
ノートブックの `KEEP_MODELS = True` で `/notebooks/models` に残せる(50GB以上使うので保存容量と料金に注意)。

動作テスト:

```bash
python /notebooks/live2d-parts-repo/scripts/run_test.py /notebooks/live2d-parts-repo/workflows/live2d_inpaint_qwen2511_fast.json
```

## ライセンス上の注意

- Qwen-Image-Edit-2511: Apache 2.0
- FLUX 3 Image Klein: FLUX Kommunity License(ゲート付き。商用は年商500万ドル未満が条件)。**重みをイメージに同梱しないこと**
- See-through / ComfyUI-See-through: 各リポジトリのライセンスに従う
