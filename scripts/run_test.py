#!/usr/bin/env python3
"""ワークフローをComfyUIのAPIで実行し、結果を機械的に検証する。

    python scripts/run_test.py workflows/live2d_inpaint_qwen2511_fast.json
    python scripts/run_test.py WORKFLOW --image my.png --mask my_mask.png --prompt "..."
    python scripts/run_test.py WORKFLOW --validate-only     # グラフの検証だけ(実行しない)

検証内容(完成パーツ *_final):
  A. マスクの外側は元画像とRGBAが完全一致(1bitも変わらない)
  B. マスクの内側は実際に描き変わっている
  C. マスクの内側は不透明、元々透明だった外側は透明のまま
"""
import argparse
import io
import json
import pathlib
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

ROOT = pathlib.Path(__file__).resolve().parent.parent
ASSETS = ROOT / "test_assets"


def http(url, data=None, headers=None, timeout=60):
    req = urllib.request.Request(url, data=data, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def upload(server, path, name):
    boundary = uuid.uuid4().hex
    body = (
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"image\"; filename=\"{name}\"\r\n"
        f"Content-Type: image/png\r\n\r\n"
    ).encode() + pathlib.Path(path).read_bytes() + (
        f"\r\n--{boundary}\r\nContent-Disposition: form-data; name=\"overwrite\"\r\n\r\ntrue\r\n--{boundary}--\r\n"
    ).encode()
    http(f"{server}/upload/image", body, {"Content-Type": f"multipart/form-data; boundary={boundary}"})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("workflow")
    ap.add_argument("--server", default="http://127.0.0.1:8188")
    ap.add_argument("--image", default=str(ASSETS / "live2d_test_image.png"))
    ap.add_argument("--mask", default=str(ASSETS / "live2d_test_mask.png"))
    ap.add_argument("--prompt", default=None, help="指示文を差し替える")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--out", default=str(ROOT / "test_outputs"))
    ap.add_argument("--timeout", type=int, default=3600)
    ap.add_argument("--validate-only", action="store_true")
    a = ap.parse_args()

    wf = json.loads(pathlib.Path(a.workflow).read_text(encoding="utf-8"))
    tag = pathlib.Path(a.workflow).stem
    names = {"1": f"{tag}__image.png", "2": f"{tag}__mask.png"}
    upload(a.server, a.image, names["1"])
    upload(a.server, a.mask, names["2"])
    wf["1"]["inputs"]["image"] = names["1"]
    wf["2"]["inputs"]["image"] = names["2"]
    if "79" in wf:
        upload(a.server, ASSETS / "live2d_test_standin.png", "live2d_test_standin.png")
    for n in wf.values():
        title = n["_meta"]["title"]
        if a.prompt and "ここを書き換える" in title:
            key = "prompt" if "prompt" in n["inputs"] else "value"
            n["inputs"][key] = a.prompt
        if a.seed is not None and n["class_type"] == "KSampler":
            n["inputs"]["seed"] = a.seed

    try:
        res = json.loads(http(f"{a.server}/prompt", json.dumps({"prompt": wf, "client_id": "live2d-test"}).encode(),
                              {"Content-Type": "application/json"}))
    except urllib.error.HTTPError as e:
        err = json.loads(e.read())
        print("VALIDATION FAILED")
        print(json.dumps(err, ensure_ascii=False, indent=2)[:6000])
        sys.exit(2)
    pid = res["prompt_id"]
    if res.get("node_errors"):
        print("node_errors:", json.dumps(res["node_errors"], ensure_ascii=False)[:3000])
    print("validated OK, prompt_id", pid)
    if a.validate_only:
        http(f"{a.server}/queue", json.dumps({"delete": [pid]}).encode(), {"Content-Type": "application/json"})
        http(f"{a.server}/interrupt", b"{}", {"Content-Type": "application/json"})
        return

    t0 = time.time()
    while True:
        hist = json.loads(http(f"{a.server}/history/{pid}"))
        if pid in hist:
            break
        if time.time() - t0 > a.timeout:
            print("TIMEOUT")
            sys.exit(3)
        time.sleep(3)
    entry = hist[pid]
    status = entry.get("status", {})
    print(f"finished in {time.time() - t0:.0f}s, status={status.get('status_str')}")
    if status.get("status_str") != "success":
        for m in status.get("messages", []):
            if m[0] == "execution_error":
                print(json.dumps(m[1], ensure_ascii=False, indent=2)[:6000])
        sys.exit(4)

    out = pathlib.Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    saved = {}
    for nid, o in entry["outputs"].items():
        for im in o.get("images", []):
            q = urllib.parse.urlencode({"filename": im["filename"], "subfolder": im["subfolder"], "type": im["type"]})
            p = out / f"{tag}__{'final' if nid == '90' else 'raw'}.png"
            p.write_bytes(http(f"{a.server}/view?{q}"))
            saved[nid] = p
            print("saved", p)

    from PIL import Image, ImageFilter
    import numpy as np

    grow = wf["4"]["inputs"]["expand"]
    blur = wf["6"]["inputs"]["blur_radius"]
    orig = np.asarray(Image.open(a.image).convert("RGBA")).astype(np.int16)
    final = np.asarray(Image.open(saved["90"]).convert("RGBA")).astype(np.int16)
    m = Image.open(a.mask).convert("L").resize((orig.shape[1], orig.shape[0]))
    core = np.asarray(m) > 127
    # 影響しうる最大範囲 = マスク + 広げ幅 + ぼかし半径 (+余裕2px)
    reach = grow + blur + 2
    outer = np.asarray(m.filter(ImageFilter.MaxFilter(2 * reach + 1))) > 0
    report = {"workflow": tag, "size_match": bool(orig.shape == final.shape)}
    if report["size_match"]:
        diff = np.abs(final - orig).max(axis=2)
        report["A_outside_max_diff"] = int(diff[~outer].max())
        report["A_outside_changed_pixels"] = int((diff[~outer] > 0).sum())
        report["B_inside_changed_ratio"] = round(float((diff[core] > 0).mean()), 4)
        report["C_inside_min_alpha"] = int(final[..., 3][core].min())
        transparent_outside = (orig[..., 3] == 0) & ~outer
        report["C_outside_transparent_kept"] = bool((final[..., 3][transparent_outside] == 0).all())
        ok = (report["A_outside_changed_pixels"] == 0 and report["B_inside_changed_ratio"] > 0.5
              and report["C_inside_min_alpha"] == 255 and report["C_outside_transparent_kept"])
    else:
        report["orig_shape"], report["final_shape"] = list(orig.shape), list(final.shape)
        ok = False
    report["result"] = "PASS" if ok else "FAIL"
    (out / f"{tag}__report.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
