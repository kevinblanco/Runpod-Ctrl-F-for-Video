#!/usr/bin/env python
"""Local web app

    python serve.py                 # talk to a running `flash dev`
    python serve.py --deployed      # talk to the deployed Runpod endpoints

Serves the viewer and a tiny search API. The API key stays in this process and is
never handed to the browser, the page asks this server, this server asks Runpod.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import numpy as np

import cli

ROOT = pathlib.Path(__file__).parent
INDEX_DIR = ROOT / "index"

ARGS = argparse.Namespace()


def load_index(name: str):
    path = INDEX_DIR / f"{name}.npz"
    if not path.exists():
        raise FileNotFoundError(name)
    d = np.load(path, allow_pickle=False)
    return d["vectors"], d["times"], str(d["video_url"])


def list_indexes() -> list[dict]:
    out = []
    for f in sorted(INDEX_DIR.glob("*.npz")):
        d = np.load(f, allow_pickle=False)
        out.append({
            "name": f.stem,
            "frames": int(len(d["times"])),
            "duration": float(d["times"][-1]) if len(d["times"]) else 0.0,
            "video_url": str(d["video_url"]),
        })
    return out


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(ROOT), **kw)

    def log_message(self, fmt, *a):  # quieter terminal during a live demo
        if "/api/" in (self.path or ""):
            super().log_message(fmt, *a)

    def _json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/":
            self.send_response(302)
            self.send_header("Location", "/viewer/")
            self.end_headers()
            return
        if self.path == "/api/indexes":
            try:
                return self._json(200, {"indexes": list_indexes()})
            except Exception as e:
                return self._json(500, {"error": str(e)})
        return super().do_GET()

    def do_POST(self):
        if self.path != "/api/search":
            return self._json(404, {"error": "not found"})
        try:
            n = int(self.headers.get("Content-Length", 0))
            req = json.loads(self.rfile.read(n) or b"{}")
            query = (req.get("query") or "").strip()
            if not query:
                return self._json(400, {"error": "query is required"})
            name = req.get("index") or (list_indexes() or [{}])[-1].get("name")
            top = max(1, min(int(req.get("top", 12)), 60))

            vectors, times, video_url = load_index(name)

            t0 = time.time()
            emb = cli.call(
                "gpu_embed/embed_text",
                ARGS.endpoint_clip,
                {"texts": [query]},
                timeout=300,
            )
            embed_ms = round((time.time() - t0) * 1000)

            q = np.asarray(emb["vectors"][0], dtype="float32")
            t1 = time.time()
            scores = vectors @ q          # both sides are L2-normalised on the GPU
            order = np.argsort(-scores)[:top]
            search_us = round((time.time() - t1) * 1e6)

            results = [{
                "rank": i + 1,
                "t": float(times[j]),
                "ts": cli.fmt_ts(float(times[j])),
                "score": round(float(scores[j]), 4),
                "frame": f"/index/{name}_frames/{float(times[j]):09.3f}.jpg",
            } for i, j in enumerate(order)]

            return self._json(200, {
                "query": query,
                "index": name,
                "video_url": video_url,
                "frames_searched": int(len(times)),
                "embed_ms": embed_ms,
                "search_us": search_us,
                "where": "deployed endpoint" if ARGS.endpoint_clip else "flash dev",
                "results": results,
            })
        except FileNotFoundError as e:
            return self._json(404, {"error": f"no index named '{e}'"})
        except SystemExit as e:
            return self._json(502, {"error": str(e)})
        except Exception as e:
            return self._json(500, {"error": f"{type(e).__name__}: {e}"})


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--port", type=int, default=8600)
    p.add_argument("--endpoint-clip", default=os.environ.get("ENDPOINT_CLIP"))
    p.add_argument("--deployed", action="store_true",
                   help="use the deployed endpoint id from ENDPOINT_CLIP")
    p.parse_args(namespace=ARGS)

    if not ARGS.deployed and not os.environ.get("ENDPOINT_CLIP"):
        ARGS.endpoint_clip = None

    where = f"deployed endpoint {ARGS.endpoint_clip}" if ARGS.endpoint_clip else \
            f"flash dev ({cli.dev_base()})"
    names = [i["name"] for i in list_indexes()]

    print(f"\n  Ctrl+F for Video   http://localhost:{ARGS.port}/viewer/")
    print(f"  queries go to      {where}")
    print(f"  indexes            {', '.join(names) or '(none — run cli.py index first)'}\n")

    ThreadingHTTPServer(("127.0.0.1", ARGS.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
