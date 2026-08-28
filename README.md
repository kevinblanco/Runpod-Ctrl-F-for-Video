# Ctrl+F for Video using Runpod

Semantic search over the *inside* of a video. Point it at a video URL, ask for
any query within the video, get the timestamp results, and click the frame to
jump the player there.

Built on [Runpod Flash](https://docs.runpod.io/flash/overview): two Python files,
no Dockerfile, deployed to Runpod Serverless with one command. **Video search you
run yourself**, your footage stays in your own account, and it scales to zero
between queries.

---

## How it works

```
   video URL
       │
       ▼
  cpu_frames.py ──── CPU worker (cpu5c-4-8)
       │             download + ffmpeg, ~1 fps, 320px JPEGs
       │             no GPU: this is I/O and codec work
       ▼
  gpu_embed.py ───── GPU worker (RTX 4090 class)
       │             CLIP ViT-B/32, model loaded ONCE per worker
       │             512-dim L2-normalised vectors
       ▼
   index/<name>.npz   ~1.2 MB for a 10-minute film
       │
       ▼
   serve.py ───────── local web app + search API
       │              cosine similarity here, in microseconds
       │              the only GPU call at query time is embedding your sentence
       ▼
   viewer/index.html  UI for the search
```

## Run it

Needs Python 3.11–3.12 and [uv](https://docs.astral.sh/uv/).

```bash
uv tool install --python 3.13 runpod-flash
uv venv --python 3.12 .venv && uv pip install -r requirements.txt

cp .env.example .env      # then put your Runpod API key in it
source bin/env.sh         # PATH, the CA-bundle, and your key
./bin/check.sh            # confirms all three before you spend anything
```

**1. Index a video.** In one terminal run `flash dev`; in another:

```bash
.venv/bin/python cli.py index \
  "https://archive.org/download/BigBuckBunny_124/Content/big_buck_bunny_720p_surround.mp4" \
  --name bigbuckbunny --max-frames 700
```

`cli.py` reads the dev server's port out of its log, because `flash dev` bumps
8888 when it's taken.

**2. Search it, in a browser.**

```bash
.venv/bin/python serve.py
```

Open <http://localhost:8600/viewer/>, type what you remember seeing, click a
result — the player jumps to that moment. The page shows you where each query was
embedded and how long it took.

Search also works from the terminal if you prefer:

```bash
.venv/bin/python cli.py search "three rodents planning something" --name bigbuckbunny
```

### Against deployed endpoints instead of `flash dev`

```bash
flash deploy
export ENDPOINT_FRAMES=<frames-id> ENDPOINT_CLIP=<clip-id>
.venv/bin/python serve.py --deployed
```

Your API key never reaches the browser, the page asks `serve.py`, and `serve.py`
asks Runpod.


## Making it better

- **Retrieval quality**: swap one string in `gpu_embed.py` for
  `google/siglip-so400m-patch14-384` and raise the GPU tier. Same code.
- **Long videos**: frames return as base64 under a 10 MB payload cap. ~3000
  frames fit; past that, window the calls or write frames to a `NetworkVolume`
  shared by both endpoints (which pins both to the same datacenter).
- **Scale**: vectors currently live in a `.npz`. At real volume this is a vector
  database, and nothing about the Flash side changes.
- **Shot detection**: 1 fps is a blunt sampler. `ffmpeg`'s scene filter would
  give better candidate frames for the same cost.

## Teardown

Endpoints scale to zero, but they still hold worker quota:

```bash
flash app delete ctrl-f-for-video
```

## Credits

Test footage is [Big Buck Bunny](https://peach.blender.org/), © Blender
Foundation, released under Creative Commons Attribution 3.0.
