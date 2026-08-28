"""Stage 1: pull candidate frames out of a video."""

from runpod_flash import CpuInstanceType, Endpoint


@Endpoint(
    name="ctrlf-frames",
    cpu=CpuInstanceType.CPU5C_4_8,
    workers=(0, 3),
    system_dependencies=["ffmpeg"], 
    dependencies=["imageio-ffmpeg"],
    idle_timeout=120,
)
async def extract(input_data: dict) -> dict:
    """Sample a video at `fps` and return base64 JPEGs with their timestamps.

    input_data:
        video_url  (str)   direct URL to a video file (mp4/webm/mov)
        fps        (float) frames sampled per second of video   [default 1.0]
        start      (float) seconds to skip from the beginning   [default 0]
        duration   (float) seconds of video to cover, 0 = all   [default 0]
        width      (int)   output frame width in px             [default 320]
    """
    import base64
    import glob
    import os
    import shutil
    import subprocess
    import tempfile
    import urllib.request

    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        import imageio_ffmpeg

        ffmpeg_bin = imageio_ffmpeg.get_ffmpeg_exe()

    max_frames_default = 240

    video_url = input_data.get("video_url")
    if not video_url:
        return {"error": "video_url is required"}

    fps = float(input_data.get("fps", 1.0))
    start = float(input_data.get("start", 0))
    duration = float(input_data.get("duration", 0))
    width = int(input_data.get("width", 320))
    max_frames = int(input_data.get("max_frames", max_frames_default))

    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "input.mp4")

        # Pull the video down first rather than letting ffmpeg stream it. Seeking
        # over HTTP re-requests byte ranges and turns a 5s job into a 60s one.
        req = urllib.request.Request(video_url, headers={"User-Agent": "ctrl-f-for-video"})
        with urllib.request.urlopen(req, timeout=300) as resp, open(src, "wb") as out:
            downloaded = 0
            while chunk := resp.read(1 << 20):
                out.write(chunk)
                downloaded += len(chunk)

        # -ss before -i is the fast seek (keyframe-accurate, and we only need
        # rough timestamps). fps=N drops us to N frames per second of source.
        cmd = [ffmpeg_bin, "-hide_banner", "-loglevel", "error", "-y"]
        if start > 0:
            cmd += ["-ss", str(start)]
        cmd += ["-i", src]
        if duration > 0:
            cmd += ["-t", str(duration)]
        cmd += [
            "-vf", f"fps={fps},scale={width}:-2",
            "-q:v", "6",
            "-frames:v", str(max_frames),
            os.path.join(tmp, "f_%05d.jpg"),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
        if proc.returncode != 0:
            return {"error": "ffmpeg failed", "stderr": proc.stderr[-2000:]}

        frames = []
        total_bytes = 0
        for path in sorted(glob.glob(os.path.join(tmp, "f_*.jpg"))):
            # index is 1-based in ffmpeg's pattern; frame i sits at start + (i-1)/fps
            idx = int(os.path.basename(path)[2:7])
            raw = open(path, "rb").read()
            total_bytes += len(raw)
            frames.append({
                "t": round(start + (idx - 1) / fps, 3),
                "jpg_b64": base64.b64encode(raw).decode(),
            })

    return {
        "frames": frames,
        "count": len(frames),
        "bytes": total_bytes,
        "source_bytes": downloaded,
        "fps": fps,
        "width": width,
        "ffmpeg": ffmpeg_bin,
    }
