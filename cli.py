#!/usr/bin/env python
"""Ctrl+F for video: local orchestrator.

    python cli.py index  <video-url> [--name NAME] [--fps 1] [--duration 0]
    python cli.py search "<query>"   [--name NAME] [--top 6]
    python cli.py list
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import pathlib
import re
import sys
import time
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).parent
INDEX_DIR = ROOT / "index"
DEV_LOG = "/tmp/flash-dev.log"


# --------------------------------------------------------------------------- transport


def dev_base() -> str:
    try:
        log = pathlib.Path(DEV_LOG).read_text()
        m = re.search(r"localhost:(\d+)", log)
        if m:
            return f"http://localhost:{m.group(1)}"
    except OSError:
        pass
    return "http://localhost:8888"


def post(url: str, payload: dict, timeout: int = 900) -> dict:
    body = json.dumps(payload).encode()
    headers = {"Content-Type": "application/json"}
    key = os.environ.get("RUNPOD_API_KEY")
    if key and "api.runpod.ai" in url:
        headers["Authorization"] = f"Bearer {key}"
    req = urllib.request.Request(url, data=body, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise SystemExit(f"HTTP {e.code} from {url}\n{e.read().decode()[:800]}") from None


def call(route: str, endpoint_id: str | None, input_data: dict, timeout: int = 900) -> dict:
    """Invoke a queue-based endpoint, dev server or deployed."""
    payload: dict = {"input_data": input_data}

    if endpoint_id:
        url = f"https://api.runpod.ai/v2/{endpoint_id}/runsync"
        if "/" in route:
            payload["method"] = route.split("/", 1)[1]
    else:
        url = f"{dev_base()}/{route}/runsync"

    res = post(url, {"input": payload}, timeout)
    out = res.get("output", res)

    if isinstance(out, dict) and out.get("status_code") == 500:
        raise SystemExit(f"worker error from {route}:\n{out.get('body', out)}")
    if isinstance(out, dict) and out.get("error"):
        raise SystemExit(f"{route}: {out['error']}")
    return out


# --------------------------------------------------------------------------- commands


def cmd_index(args) -> None:
    import numpy as np

    name = args.name or slug(args.video_url)
    frames_dir = INDEX_DIR / f"{name}_frames"
    frames_dir.mkdir(parents=True, exist_ok=True)

    print(f"[1/3] extracting frames on a CPU worker  ({args.fps} fps)")
    t0 = time.time()
    got = call(
        "cpu_frames",
        args.endpoint_frames,
        {
            "video_url": args.video_url,
            "fps": args.fps,
            "start": args.start,
            "duration": args.duration,
            "width": args.width,
            "max_frames": args.max_frames,
        },
    )
    frames = got["frames"]
    t_frames = time.time() - t0
    print(
        f"      {got['count']} frames · {got['bytes'] / 1024:.0f} KB payload "
        f"· {got['source_bytes'] / 1e6:.1f} MB source · {t_frames:.1f}s"
    )

    for f in frames:
        (frames_dir / f"{f['t']:09.3f}.jpg").write_bytes(base64.b64decode(f["jpg_b64"]))

    print("[2/3] embedding frames on a GPU worker  (CLIP ViT-B/32)")
    t0 = time.time()
    emb = call(
        "gpu_embed/embed_images",
        args.endpoint_clip,
        {"images_b64": [f["jpg_b64"] for f in frames], "batch_size": args.batch_size},
    )
    t_embed = time.time() - t0
    print(f"      {emb['count']} vectors · {emb['dim']} dims · {t_embed:.1f}s")

    print("[3/3] saving index")
    vectors = np.asarray(emb["vectors"], dtype="float32")
    times = np.asarray([f["t"] for f in frames], dtype="float32")
    INDEX_DIR.mkdir(exist_ok=True)
    np.savez(
        INDEX_DIR / f"{name}.npz",
        vectors=vectors,
        times=times,
        video_url=args.video_url,
    )
    size = (INDEX_DIR / f"{name}.npz").stat().st_size
    print(
        f"\n  indexed '{name}': {len(times)} frames, {size / 1024:.0f} KB on disk\n"
        f"  frames {t_frames:.1f}s + embed {t_embed:.1f}s = {t_frames + t_embed:.1f}s total\n"
        f"\n  now:  python cli.py search \"something you remember seeing\" --name {name}"
    )


def cmd_search(args) -> None:
    import numpy as np

    name = args.name or default_index()
    path = INDEX_DIR / f"{name}.npz"
    if not path.exists():
        raise SystemExit(f"no index named '{name}'. run `python cli.py list`")

    data = np.load(path, allow_pickle=False)
    vectors, times = data["vectors"], data["times"]
    video_url = str(data["video_url"])

    t0 = time.time()
    emb = call("gpu_embed/embed_text", args.endpoint_clip, {"texts": [args.query]}, timeout=300)
    q = np.asarray(emb["vectors"][0], dtype="float32")

    # Both sides are L2-normalised on the GPU, so cosine similarity is just a dot
    # product. 500 frames x 512 dims is a rounding error of compute.
    scores = vectors @ q
    top = np.argsort(-scores)[: args.top]
    dt = time.time() - t0

    print(f'\n  "{args.query}"  in {name}   ({dt:.2f}s, {len(times)} frames searched)\n')
    for rank, i in enumerate(top, 1):
        t = float(times[i])
        print(f"  {rank}.  {fmt_ts(t):>9}   score {scores[i]:.3f}")

    print(
        "\n  see them:  python serve.py --deployed"
        "   then open http://localhost:8600/viewer/\n"
    )


def cmd_list(args) -> None:
    import numpy as np

    files = sorted(INDEX_DIR.glob("*.npz"))
    if not files:
        raise SystemExit("no indexes yet. run `python cli.py index <video-url>`")
    for f in files:
        d = np.load(f, allow_pickle=False)
        print(f"  {f.stem:<28} {len(d['times']):>5} frames   {str(d['video_url'])[:60]}")


# --------------------------------------------------------------------------- helpers


def slug(url: str) -> str:
    base = url.rstrip("/").split("/")[-1].split("?")[0]
    return re.sub(r"[^a-zA-Z0-9_-]+", "-", base.rsplit(".", 1)[0])[:40] or "video"


def default_index() -> str:
    files = sorted(INDEX_DIR.glob("*.npz"))
    if not files:
        raise SystemExit("no indexes yet. run `python cli.py index <video-url>`")
    return files[-1].stem


def fmt_ts(t: float) -> str:
    return f"{int(t) // 60}:{int(t) % 60:02d}.{int((t % 1) * 10)}"


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--endpoint-frames", default=os.environ.get("ENDPOINT_FRAMES"),
                   help="deployed endpoint id for cpu_frames (default: talk to flash dev)")
    p.add_argument("--endpoint-clip", default=os.environ.get("ENDPOINT_CLIP"),
                   help="deployed endpoint id for gpu_embed (default: talk to flash dev)")
    sub = p.add_subparsers(dest="cmd", required=True)

    i = sub.add_parser("index", help="index a video")
    i.add_argument("video_url")
    i.add_argument("--name")
    i.add_argument("--fps", type=float, default=1.0)
    i.add_argument("--start", type=float, default=0)
    i.add_argument("--duration", type=float, default=0)
    i.add_argument("--width", type=int, default=320)
    i.add_argument("--batch-size", type=int, default=64)
    i.add_argument("--max-frames", type=int, default=240,
                   help="cap per call; frames come back as base64 under a 10MB payload limit")
    i.set_defaults(func=cmd_index)

    s = sub.add_parser("search", help="search an index")
    s.add_argument("query")
    s.add_argument("--name")
    s.add_argument("--top", type=int, default=6)
    s.set_defaults(func=cmd_search)

    ls = sub.add_parser("list", help="list local indexes")
    ls.set_defaults(func=cmd_list)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    sys.exit(main())
