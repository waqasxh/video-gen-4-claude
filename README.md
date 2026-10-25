# Gemini Video Gen Plugin for Claude Code

A Claude Code plugin for generating videos using Google's Gemini API (Veo).

## What This Plugin Does

This plugin enables Claude Code to generate short videos using Google's Gemini API. When you ask Claude to create,
generate, or animate a video, it will use this plugin automatically.

Features:

- Generate videos (4-8 seconds, with audio) from text prompts
- Animate an existing image (image-to-video)
- Use up to 3 reference images for subject/style consistency
- 16:9 and 9:16 aspect ratios, 720p and 1080p
- Fast or higher-quality Veo model
- Batch generation of multiple videos
- Reusable style templates

## Requirements

- [uv](https://docs.astral.sh/uv/) package manager
- Google AI API key from [Google AI Studio](https://aistudio.google.com/apikey) with **billing enabled**
  (Veo video generation is a paid API feature)

## Installation

### 1. Add the Marketplace & Install

In Claude Code, run:

```
/plugin marketplace add waqasxh/video-gen-4-claude
/plugin install video-gen-4-claude@video-gen-4-claude
```

### 2. Set Your API Key

**Option A: Config file (recommended)**

```bash
mkdir -p ~/.config/video-gen-4-claude
echo "GOOGLE_AI_API_KEY=your_actual_api_key_here" > ~/.config/video-gen-4-claude/.env
```

**Option B: Environment variable**

```bash
export GOOGLE_AI_API_KEY=your_actual_api_key_here
# Add to your shell profile (~/.zshrc, ~/.bashrc) for persistence
```

### 3. Done

Claude Code will automatically detect and use the plugin when you ask it to generate videos.

## Usage Examples

Just ask Claude Code naturally:

### Text to Video

```
Generate a video of a paper boat drifting down a rainy street and save it as boat.mp4
```

```
Create a 6 second cinematic aerial shot of a coastline at sunrise, save as coast.mp4
```

### Vertical Video

```
Make a vertical 9:16 video of a barista pouring latte art, save as story.mp4
```

### Animating an Image

```
Animate photo.png: the camera slowly pushes in while clouds drift across the sky
```

### Using Reference Images

```
Generate a video of the fox in fox.png running through a snowy forest
```

### Higher Quality

```
Generate a 1080p video of a city at dusk using the quality model
```

### Multiple Videos

```
Generate 3 videos: a cat on a sofa, a dog on a beach, and a bird on a wire
```

### With Style Templates

You can create custom style templates as markdown files with a `## Prompt Template` section:

```markdown
## Prompt Template

\```
Cinematic 35mm film look, shallow depth of field, warm tones, slow camera movement.
{subject}
\```
```

Then ask Claude:

```
Generate a video of a lighthouse in a storm using the style template my-style.md
```

## Cost & Confirmation

Veo has **no free tier**: every generated video is billed to your Google API key. The plugin never spends money on
its own:

- The script refuses to call the API unless `--paid` is passed, and exits with code `3` instead.
- Claude asks you to confirm before every generation and only then adds `--paid`. The approval applies to that
  request only.
- From the command line, pass `--paid` yourself to confirm.

| Option      | Default model                   | Override env var             |
|-------------|---------------------------------|------------------------------|
| (default)   | `veo-3.1-fast-generate-preview` | `GEMINI_VIDEO_MODEL`         |
| `--quality` | `veo-3.1-generate-preview`      | `GEMINI_VIDEO_MODEL_QUALITY` |

> Model names and pricing change; see Google's current Gemini API pricing page. If a model name is rejected, set the
> env var to a currently listed Veo model.

## Options

| Option         | Short | Description                                                        |
|----------------|-------|--------------------------------------------------------------------|
| `--style`      | `-s`  | Style template (.md file with `{subject}` placeholder)             |
| `--image`      | `-i`  | Image used as the first frame                                      |
| `--ref`        | `-r`  | Reference image (repeatable, max 3; requires 16:9 and 8 seconds)  |
| `--aspect`     | `-a`  | `16:9` (default) or `9:16`                                         |
| `--duration`   | `-d`  | `4`, `6` or `8` seconds (default 8)                                |
| `--resolution` |       | `720p` (default) or `1080p` (requires 8 seconds)                   |
| `--negative`   |       | Things to keep out of the video                                    |
| `--quality`    |       | Higher-quality, slower, pricier model                              |
| `--timeout`    |       | Seconds to wait per video (default 900)                            |
| `--paid`       |       | Confirm that charges are OK                                        |

A single video usually takes 1-6 minutes to generate.

## Troubleshooting

| Error                                     | Cause                               | Solution                                                       |
|-------------------------------------------|-------------------------------------|----------------------------------------------------------------|
| `GOOGLE_AI_API_KEY not found`             | Missing API key                     | Create `~/.config/video-gen-4-claude/.env` with your API key   |
| Exit code `3` / `PAID_CONFIRMATION_REQUIRED` | `--paid` not passed              | Confirm the charges, then re-run with `--paid`                 |
| Exit code `3` / `BILLING_UNAVAILABLE`     | No quota or billing on the key      | Enable billing for your key in Google AI Studio                |
| `Timed out after ...`                     | Video took longer than `--timeout`  | Retry, or raise `--timeout`                                    |
| `No video returned. Filtered: ...`        | Safety filter blocked the prompt    | Rephrase the prompt or use a different image                   |
| `uv: command not found`                   | uv not installed                    | Install via `curl -LsSf https://astral.sh/uv/install.sh \| sh` |

## Development

### Local Testing

```bash
claude --plugin-dir .
uv run pytest
```

### Versioning & Updates

Bump `version` in `plugin.json` (semver) and push to `main`. Claude Code pulls the latest commit from the default
branch — git tags are currently ignored. Optionally tag for your own release tracking:

```bash
git tag 2.0.0 && git push origin 2.0.0
```

Users receive updates via `/plugin update` or automatic update checks.

### Architecture Overview

| Component               | Role                                               |
|-------------------------|----------------------------------------------------|
| `skills/…/SKILL.md`     | Loaded into Claude's context as skill prompt       |
| `main.py`, `scripts/`   | Executed via Bash by Claude                        |
| `${CLAUDE_PLUGIN_ROOT}` | Plugin cache path (where plugin files live)        |
| `--cwd` / working dir   | User's project path (where output files are saved) |

## Credits

This is a fork of [ypfaff/google-image-gen-plugin](https://github.com/ypfaff/google-image-gen-plugin) by Yannick Pfaff
(MIT), which is based on the work
from [AI Engineer Skool's Google Image Gen API Starter](https://github.com/AI-Engineer-Skool/google-image-gen-api-starter).
It was converted from image to video generation.

For more infos, check out the corresponding [video guide](https://youtu.be/NBibgD7I48w?si=ucFFgKFgyx5FxA-0).

## License

[MIT](LICENSE)
