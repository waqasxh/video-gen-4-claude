---
name: video-gen-4-claude
description: >
  Generate videos using Google's Gemini API (Veo). Use this skill when the user wants
  to generate, create, or animate videos with AI. Keywords: video generation,
  create video, generate clip, text to video, image to video, animate image,
  AI video, Veo, Gemini, mp4.
allowed-tools: Bash, Read, Glob, AskUserQuestion
---

# Gemini Video Gen Skill

Generate short videos (4-8 seconds, with audio) from text prompts, or animate an image, using
Google's Gemini API (Veo models).

## Paid: always confirm first

Veo video generation has **no free tier**: every run is billed to the user's Google API key.
The script refuses to call the API unless `--paid` is passed. You must **never** pass `--paid`
unless the user has explicitly confirmed charges in this conversation for this request.

### Confirmation flow

1. Before the first run for a request, ask with AskUserQuestion, for example: "Video generation
   with Gemini (Veo) is a paid API feature. Generate this <N>s <resolution> video with
   <fast|quality> model?" Options: yes, generate / change settings / cancel. Mention that
   `--quality` and `--resolution 1080p` cost more and take longer.
2. Only on a clear yes, run the command **with** `--paid`. Approval covers that request only;
   ask again next time.
3. If a command without `--paid` is run, it exits with code **3** (`PAID_CONFIRMATION_REQUIRED`)
   and sends nothing. Treat that as the cue to ask.
4. Exit code **3** with `BILLING_UNAVAILABLE` means the key has no quota or billing. Tell the
   user (they need billing enabled at https://aistudio.google.com) rather than retrying.

Skipping the question is only acceptable when the user already said to go ahead and pay in their
original request (e.g. "generate it, I know it costs money").

### Models

| Option      | Default model                    | Override env var              |
|-------------|----------------------------------|-------------------------------|
| (default)   | `veo-3.1-fast-generate-preview`  | `GEMINI_VIDEO_MODEL`          |
| `--quality` | `veo-3.1-generate-preview`       | `GEMINI_VIDEO_MODEL_QUALITY`  |

Model availability changes over time. If the API rejects a model name, the user can set the env
var to a currently listed Veo model.

## First-Time Setup (Once Per Context)

Run these commands once at the start of a session:

```bash
"${CLAUDE_PLUGIN_ROOT}/scripts/check_env.sh"
uv sync --project "${CLAUDE_PLUGIN_ROOT}"
```

If the environment check fails, the user needs to configure their API key.
Recommended: Create `~/.config/video-gen-4-claude/.env` with:

```
GOOGLE_AI_API_KEY=your_key_here
```

Get an API key from https://aistudio.google.com/apikey

Alternative: Export as environment variable: `export GOOGLE_AI_API_KEY=your_key`

## Usage

The plugin runs from its own directory. Pass `--cwd "$PWD"` so output files land in the user's
project, not the plugin cache.

```bash
uv run --project "${CLAUDE_PLUGIN_ROOT}" python "${CLAUDE_PLUGIN_ROOT}/main.py" --cwd "$PWD" <output_path.mp4> "<prompt>" [options]
```

The output must be an `.mp4` path. When the user specifies a path like `clip.mp4` or
`videos/intro.mp4`, pass it as-is; `--cwd` resolves it relative to the user's project root.

A single video takes roughly 1-6 minutes (the script polls until it is ready). Run the command
with a long Bash timeout (e.g. 600000 ms) or in the background, and tell the user it may take a
few minutes.

## Options

| Option         | Short | Description                                                                 |
|----------------|-------|-----------------------------------------------------------------------------|
| `--style`      | `-s`  | Style template (.md file with `{subject}` placeholder)                      |
| `--image`      | `-i`  | Image used as the first frame (image-to-video)                              |
| `--ref`        | `-r`  | Reference image for subject/style (repeatable, max 3; needs 16:9 and 8s)    |
| `--aspect`     | `-a`  | `16:9` (default) or `9:16`                                                  |
| `--duration`   | `-d`  | `4`, `6` or `8` seconds (default 8)                                         |
| `--resolution` |       | `720p` (default) or `1080p` (1080p requires `--duration 8`)                 |
| `--negative`   |       | Negative prompt: things to keep out of the video                            |
| `--quality`    |       | Higher-quality, slower and pricier model                                    |
| `--timeout`    |       | Seconds to wait per video (default 900)                                     |
| `--paid`       |       | Confirms charges are OK. Only after user confirmation (see above)           |

Style templates are markdown files with a `## Prompt Template` heading followed by a fenced code
block containing the prompt and a `{subject}` placeholder.

## Prompting tips

Describe the subject, action, camera movement (dolly, pan, aerial, handheld), lighting and mood.
Veo also generates audio, so dialogue in quotes and sound descriptions ("distant thunder") work.
Use `--negative` for unwanted elements instead of writing "no ..." in the prompt.

## Exit codes

| Code | Meaning                                                          | What to do                                  |
|------|------------------------------------------------------------------|---------------------------------------------|
| 0    | All videos saved                                                 | Verify and report                           |
| 1    | Generation failed (API error, blocked, timeout, no video)        | Show the message; adjust the prompt/retry   |
| 2    | Invalid input (missing file, bad option combo, no API key)       | Fix the input or setup                      |
| 3    | `--paid` missing, or quota/billing unavailable                   | Ask the user (see confirmation flow)        |

## Examples

In the examples, `RUN` stands for
`uv run --project "${CLAUDE_PLUGIN_ROOT}" python "${CLAUDE_PLUGIN_ROOT}/main.py" --cwd "$PWD"`.
All of them need `--paid` after the user confirmed.

```bash
# Text to video
RUN clip.mp4 "A paper boat drifting down a rainy street, cinematic, slow dolly" --paid

# Vertical video for Stories/TikTok, shorter
RUN videos/story.mp4 "A barista pouring latte art" --aspect 9:16 --duration 6 --paid

# Animate an image
RUN clip.mp4 "The camera slowly pushes in as clouds move" --image photo.png --paid

# Reference images for a consistent subject
RUN clip.mp4 "The fox runs through a snowy forest" --ref fox.png --paid

# Best quality
RUN clip.mp4 "Aerial shot of a coastline at sunrise" --quality --resolution 1080p --paid

# Several videos -> clip_1.mp4, clip_2.mp4
RUN clip.mp4 "a cat on a sofa" "a dog on a beach" --paid
```

(Write the full command each time; `RUN` is shorthand only.)

## Workflow

1. First use in context: run the setup commands (check_env.sh + uv sync).
2. Ask the user to confirm the paid generation and settings.
3. Run with `--paid`, allowing several minutes.
4. Check the exit code and confirm the `.mp4` exists (Glob/Bash `ls`). You cannot view video
   frames, so don't claim to have verified the content.
5. Report the output path and the model/settings used.

## Notes

- Existing output files are overwritten. Choose a new name if the user wants to keep the old one.
- With several prompts, a failed video doesn't stop the others; the exit code is 1 if any failed.
- Prompts and images are sent to Google's API. Generated videos may carry a SynthID watermark.
- Veo can refuse prompts or images that trip safety filters (people in image-to-video are
  restricted in some regions); the script prints the reason when the API gives one.
