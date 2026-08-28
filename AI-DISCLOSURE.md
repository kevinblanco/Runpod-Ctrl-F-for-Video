# How AI was used to build this

The exercise invites AI assistance and asks that it be disclosed. Here is the
honest account.

## What I used

**Claude Code (Opus 5)**, with Runpod's own
[Claude Code plugin](https://github.com/runpod/runpod-claude-plugin) installed —
the one that ships the `flash`, `runpodctl`, `runpod-mcp` and `runpod-usage`
skills. Using a vendor's own agent tooling to evaluate that vendor's product felt
like the most honest version of "what would a developer actually do in 2026."

## What it did

- Read the Flash docs, the launch blog post, the GitHub README and the plugin's
  bundled skill references, and summarised the API surface and known gotchas
  before I wrote any code.
- Wrote first drafts of `cpu_frames.py`, `gpu_embed.py`, `cli.py` and the viewer.
- Ran the terminal loop with me: `flash dev`, `curl`, read worker logs, `flash
  deploy`, teardown.
- Diagnosed the failures in [`FRICTION.md`](FRICTION.md) — including writing the
  throwaway probe that revealed the transformers 5.x return type.
- Drafted this repo's prose, and the outline and script in
  [`presentation/`](presentation/).

## What I did

- **Chose the use case.** Video frame search, and specifically the "the model was
  never the blocker, the deployment was" framing, is the argument I want to make.
  That is the part of a DevRel talk that cannot be delegated.
- **Chose the architecture.** The CPU/GPU split exists because I wanted the cost
  argument on screen, not because it was the shortest path to working code.
- **Verified every claim.** Every number in the README and the deck came off my
  own terminal. I opened the returned frames and confirmed that "a dragon flying"
  is a dragon flying. No benchmark in this repo is estimated or repeated from
  marketing material.
- **Own the friction log.** The findings are real and reproducible; #9 in
  particular is a genuine dev/prod parity bug I would file upstream.

## Where AI actively made things worse

Worth saying plainly, because it's the interesting part.

The transformers 5.x bug (FRICTION #7) was *introduced* by an AI-written fallback
that looked reasonable and produced vectors passing every shape and norm check
while being semantically meaningless. A confident wrong answer that validates
cleanly is exactly the failure mode you get from generated code, and no amount of
review-by-reading would have caught it — only looking at real output did.

That is the thing I would want to say to a room of developers about building with
AI on GPU infrastructure: it will get you to a running endpoint remarkably fast,
and it will not tell you when the endpoint is confidently wrong. **Verify the
output, not the code.**
