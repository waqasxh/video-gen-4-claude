#!/usr/bin/env python3
"""Gemini Video Generator.

Generate videos from text prompts, or animate an existing image, using Google's
Gemini API (Veo models). Supports reference images and style templates.

This script is part of the video-gen-4-claude Claude Code plugin.

Setup:
    1. Get API key from https://aistudio.google.com/apikey
    2. Create ~/.config/video-gen-4-claude/.env with: GOOGLE_AI_API_KEY=your_key_here
       Or export GOOGLE_AI_API_KEY=your_key_here
    3. Run: uv sync (or pip install google-genai python-dotenv)

Cost:
    Veo video generation is a paid feature of the Gemini API (billing must be
    enabled on the key) and every run costs money. The script therefore refuses
    to call the API unless --paid is passed (the skill only passes it after the
    user confirmed). If the API reports quota/billing problems the script exits
    with code 3.

    Models can be overridden with GEMINI_VIDEO_MODEL / GEMINI_VIDEO_MODEL_QUALITY.

Usage:
    uv run python main.py output.mp4 "A paper boat drifting down a rainy street" --paid
    uv run python main.py output.mp4 "Slow dolly in" --image start.png --paid
    uv run python main.py output.mp4 "A fox in a forest" --ref fox.png --paid
    uv run python main.py output.mp4 "A city at dusk" --aspect 9:16 --duration 6 --paid
    uv run python main.py output.mp4 "A city at dusk" --resolution 1080p --quality --paid
    uv run python main.py output.mp4 "cube" "sphere" --style my_style.md --paid
    uv run python main.py --cwd /path/to/project output.mp4 "Prompt" --paid

Exit codes:
    0  all videos saved
    1  generation failed (API error, blocked, timeout, or no video returned)
    2  invalid input (missing file, bad option combination, missing API key, ...)
    3  paid confirmation missing, or quota/billing unavailable; ask the user
"""
import argparse
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Callable, Optional

from dotenv import load_dotenv
from google import genai
from google.genai import errors as genai_errors
from google.genai import types

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_BAD_INPUT = 2
EXIT_PAID_REQUIRED = 3

DEFAULT_MODEL = "veo-3.1-fast-generate-preview"
QUALITY_MODEL = "veo-3.1-generate-preview"

MAX_REFERENCES = 3
DURATIONS = (4, 6, 8)
RESOLUTIONS = ("720p", "1080p")
ASPECTS = ("16:9", "9:16")

DEFAULT_TIMEOUT_S = 900
DEFAULT_POLL_S = 10

_IMAGE_MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}

_QUOTA_MARKERS = (
    "resource_exhausted",
    "quota",
    "billing",
    "free tier",
    "free_tier",
    "limit: 0",
    "paid",
    "permission_denied",
)


class BillingUnavailable(Exception):
    """The API cannot serve this request (quota exhausted or billing required)."""


class GenerationError(Exception):
    """Generation failed for a reason other than billing/quota."""


def load_style_template(style_path: Path) -> str:
    """Load a prompt template from a markdown style file.

    Looks for a code block after '## Prompt Template' or '### Template'.
    The template should contain {subject} as a placeholder.

    Raises:
        FileNotFoundError: If style file doesn't exist.
        ValueError: If no prompt template found in file.
    """
    if not style_path.exists():
        raise FileNotFoundError(f"Style file not found: {style_path}")

    content = style_path.read_text(encoding="utf-8")

    # Look for code block after "Prompt Template" or "Template" header
    pattern = (
        r'(?:##?\s*(?:Prompt\s*)?Template)[^\n]*\n+(?:.*?\n)*?```[^\n]*\n(.*?)```'
    )
    match = re.search(pattern, content, re.IGNORECASE | re.DOTALL)

    if match:
        template = match.group(1).strip()
        # Normalize the placeholder
        return re.sub(
            r'\[YOUR SUBJECT[^\]]*\]|\[SUBJECT\]|\{subject\}',
            '{subject}',
            template,
            flags=re.IGNORECASE,
        )

    raise ValueError(
        f"No prompt template found in {style_path}. "
        "Add a '## Prompt Template' section with a code block."
    )


def apply_style_template(template: str, subject: str) -> str:
    """Apply a subject to a style template.

    Uses plain replacement (not str.format) so other braces in the template,
    e.g. JSON snippets, are left untouched.
    """
    if '{subject}' in template:
        return template.replace('{subject}', subject)
    # If no placeholder, prepend the subject
    return f"{subject}. {template}"


def validate_options(
    duration: int, resolution: str, aspect: str, num_references: int
) -> Optional[str]:
    """Return an error message for option combinations Veo rejects, else None."""
    if resolution == "1080p" and duration != 8:
        return "--resolution 1080p requires --duration 8"
    if num_references:
        if num_references > MAX_REFERENCES:
            return f"at most {MAX_REFERENCES} reference images are supported"
        if duration != 8:
            return "--ref requires --duration 8"
        if aspect != "16:9":
            return "--ref requires --aspect 16:9"
    return None


def _load_image(path: Path) -> types.Image:
    """Read an image file into a Gemini image part."""
    mime = _IMAGE_MIME.get(path.suffix.lower())
    if mime is None:
        raise ValueError(f"Unsupported image type: {path.suffix} (use png, jpg or webp)")
    return types.Image(image_bytes=path.read_bytes(), mime_type=mime)


def _is_quota_error(exc: genai_errors.APIError) -> bool:
    """Whether an API error means billing/quota prevents the request."""
    if exc.code == 429:
        return True
    text = f"{exc.status or ''} {exc.message or ''}".lower()
    if exc.code in (400, 402, 403) and any(m in text for m in _QUOTA_MARKERS):
        return True
    return "resource_exhausted" in text or "limit: 0" in text


def _wait_for_operation(
    client: Any,
    operation: Any,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    poll_s: float = DEFAULT_POLL_S,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> Any:
    """Poll a long-running video operation until it finishes.

    Raises:
        GenerationError: If the operation does not finish within timeout_s.
    """
    deadline = clock() + timeout_s
    while not operation.done:
        if clock() >= deadline:
            raise GenerationError(f"Timed out after {timeout_s:.0f}s waiting for the video")
        sleep(poll_s)
        operation = client.operations.get(operation)
    return operation


def generate(
    prompt: str,
    output_path: Path,
    model: str,
    image: Optional[types.Image] = None,
    references: Optional[list[types.Image]] = None,
    aspect_ratio: str = "16:9",
    resolution: str = "720p",
    duration: int = 8,
    negative_prompt: Optional[str] = None,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    poll_s: float = DEFAULT_POLL_S,
) -> None:
    """Request one video, wait for it, and save it.

    Args:
        prompt: Text prompt describing the video.
        output_path: Where to save the .mp4.
        model: Veo model ID.
        image: Optional first frame to animate (image-to-video).
        references: Optional reference images (subject/style guidance).
        aspect_ratio: "16:9" or "9:16".
        resolution: "720p" or "1080p".
        duration: Length in seconds (4, 6 or 8).
        negative_prompt: Things to keep out of the video.
        timeout_s: Give up waiting after this many seconds.
        poll_s: Seconds between status checks.

    Raises:
        BillingUnavailable: Quota/billing error from the API.
        GenerationError: Any other failure, including responses without a video.
    """
    client = genai.Client(api_key=os.environ.get("GOOGLE_AI_API_KEY"))

    config_kwargs: dict[str, Any] = {
        "number_of_videos": 1,
        "aspect_ratio": aspect_ratio,
        "resolution": resolution,
        "duration_seconds": duration,
    }
    if negative_prompt:
        config_kwargs["negative_prompt"] = negative_prompt
    if references:
        config_kwargs["reference_images"] = [
            types.VideoGenerationReferenceImage(image=ref, reference_type="asset")
            for ref in references
        ]

    try:
        operation = client.models.generate_videos(
            model=model,
            prompt=prompt,
            image=image,
            config=types.GenerateVideosConfig(**config_kwargs),
        )
        operation = _wait_for_operation(client, operation, timeout_s, poll_s)
    except genai_errors.APIError as exc:
        if _is_quota_error(exc):
            raise BillingUnavailable(f"{exc.code} {exc.status}: {exc.message}") from exc
        raise GenerationError(f"API error {exc.code} {exc.status}: {exc.message}") from exc

    if operation.error:
        raise GenerationError(f"Operation failed: {operation.error}")

    response = operation.response
    videos = (response.generated_videos if response else None) or []
    if not videos or not videos[0].video:
        reason = ""
        if response and getattr(response, "rai_media_filtered_reasons", None):
            reason = "Filtered: " + "; ".join(response.rai_media_filtered_reasons)
        raise GenerationError(f"No video returned. {reason}".strip())

    try:
        client.files.download(file=videos[0].video)
        videos[0].video.save(str(output_path))
    except genai_errors.APIError as exc:
        raise GenerationError(f"Download failed: {exc.code} {exc.status}: {exc.message}") from exc
    print(f"Video saved to: {output_path} (model: {model})")


def _resolve_path(path: Path, base_dir: Path) -> Path:
    """Resolve a relative path against a base directory."""
    if path.is_absolute():
        return path
    return base_dir / path


def _load_env(script_dir: Path, base_dir: Path) -> None:
    """Load .env files; earlier sources win over later ones."""
    # 1. User home config (primary recommended location)
    home_env = Path.home() / ".config" / "video-gen-4-claude" / ".env"
    if home_env.exists():
        load_dotenv(home_env)

    # 2. Plugin/script directory .env (for development)
    env_path = script_dir / ".env"
    if env_path.exists():
        load_dotenv(env_path, override=False)

    # 3. User's project directory .env (fallback)
    project_env = base_dir / ".env"
    if project_env.exists():
        load_dotenv(project_env, override=False)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate videos using the Google Gemini API (Veo). Paid; needs --paid.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py output.mp4 "A paper boat in the rain" --paid
  python main.py output.mp4 "Slow dolly in" --image start.png --paid
  python main.py output.mp4 "A fox in a forest" --ref fox.png --paid
  python main.py output.mp4 "City at dusk" --aspect 9:16 --duration 6 --paid
  python main.py output.mp4 "City at dusk" --resolution 1080p --quality --paid
  python main.py --cwd /path/to/project output.mp4 "Prompt" --paid

Exit codes: 0 ok, 1 failed, 2 invalid input, 3 paid confirmation/billing needed.
        """,
    )
    parser.add_argument("output", help="Output path for the video (.mp4)")
    parser.add_argument("prompts", nargs="+", help="One or more prompts/subjects")
    parser.add_argument("--style", "-s", help="Path to style template .md file")
    parser.add_argument("--image", "-i", help="Image to use as the first frame (image-to-video)")
    parser.add_argument(
        "--ref", "-r",
        action="append",
        dest="references",
        help=f"Reference image for subject/style (repeatable, up to {MAX_REFERENCES})",
    )
    parser.add_argument(
        "--aspect", "-a", default="16:9", choices=ASPECTS,
        help="Aspect ratio (default: 16:9)",
    )
    parser.add_argument(
        "--duration", "-d", type=int, default=8, choices=DURATIONS,
        help="Length in seconds (default: 8)",
    )
    parser.add_argument(
        "--resolution", default="720p", choices=RESOLUTIONS,
        help="Resolution (default: 720p; 1080p requires --duration 8)",
    )
    parser.add_argument("--negative", help="Negative prompt: things to keep out of the video")
    parser.add_argument(
        "--quality", action="store_true",
        help="Use the higher-quality (slower, pricier) Veo model instead of the fast one",
    )
    parser.add_argument(
        "--timeout", type=int, default=DEFAULT_TIMEOUT_S,
        help=f"Seconds to wait per video (default: {DEFAULT_TIMEOUT_S})",
    )
    parser.add_argument(
        "--paid",
        action="store_true",
        help="Confirm that charges are OK. Only pass after the user confirmed.",
    )
    parser.add_argument(
        "--cwd",
        help="Base directory for resolving relative paths (default: current directory)",
    )
    return parser


def main() -> int:
    """Main entry point. Returns an exit code (see module docstring)."""
    args = _build_parser().parse_args()

    base_dir = Path(args.cwd) if args.cwd else Path.cwd()
    script_dir = Path(__file__).parent
    _load_env(script_dir, base_dir)

    if not os.environ.get("GOOGLE_AI_API_KEY"):
        print("Error: GOOGLE_AI_API_KEY not found in environment")
        print("Set up your API key using one of these methods:")
        print("  1. Create ~/.config/video-gen-4-claude/.env with: GOOGLE_AI_API_KEY=your_key_here")
        print("  2. Export: export GOOGLE_AI_API_KEY=your_key_here")
        print("Get your API key from: https://aistudio.google.com/apikey")
        return EXIT_BAD_INPUT

    output_path = _resolve_path(Path(args.output), base_dir)
    if output_path.suffix.lower() != ".mp4":
        print(f"Error: output must be an .mp4 file, got: {output_path.name}")
        return EXIT_BAD_INPUT

    error = validate_options(args.duration, args.resolution, args.aspect, len(args.references or []))
    if error:
        print(f"Error: {error}")
        return EXIT_BAD_INPUT

    model = (
        os.environ.get("GEMINI_VIDEO_MODEL_QUALITY") or QUALITY_MODEL
        if args.quality
        else os.environ.get("GEMINI_VIDEO_MODEL") or DEFAULT_MODEL
    )

    # Load style template if provided
    prompts = args.prompts
    if args.style:
        style_path = _resolve_path(Path(args.style), base_dir)
        # If resolved path doesn't exist, also check relative to script directory
        if not style_path.exists() and (script_dir / args.style).exists():
            style_path = script_dir / args.style
        try:
            template = load_style_template(style_path)
        except (FileNotFoundError, ValueError) as e:
            print(f"Error: {e}")
            return EXIT_BAD_INPUT
        print(f"Loaded style template from: {style_path}")
        prompts = [apply_style_template(template, p) for p in prompts]

    # Load input images up front so bad paths fail before any API call
    start_image: Optional[types.Image] = None
    if args.image:
        image_path = _resolve_path(Path(args.image), base_dir)
        if not image_path.exists():
            print(f"Error: Input image not found: {image_path}")
            return EXIT_BAD_INPUT
        try:
            start_image = _load_image(image_path)
        except ValueError as e:
            print(f"Error: {e}")
            return EXIT_BAD_INPUT

    ref_paths = [_resolve_path(Path(r), base_dir) for r in args.references or []]
    missing = [p for p in ref_paths if not p.exists()]
    if missing:
        for p in missing:
            print(f"Error: Reference image not found: {p}")
        return EXIT_BAD_INPUT
    try:
        references = [_load_image(p) for p in ref_paths]
    except ValueError as e:
        print(f"Error: {e}")
        return EXIT_BAD_INPUT

    if not args.paid:
        print(f"PAID_CONFIRMATION_REQUIRED: video generation is a paid Gemini API feature (model: {model}).")
        print("No request was sent. Ask the user to confirm charges, then re-run with --paid.")
        return EXIT_PAID_REQUIRED

    print(f"Model: {model} ({args.resolution}, {args.duration}s, {args.aspect})")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if len(prompts) == 1:
        jobs = [(prompts[0], output_path)]
    else:
        jobs = [
            (p, output_path.parent / f"{output_path.stem}_{i}{output_path.suffix}")
            for i, p in enumerate(prompts, 1)
        ]

    failures = 0
    for i, (prompt, path) in enumerate(jobs, 1):
        if len(jobs) > 1:
            print(f"\nGenerating video {i}/{len(jobs)}...")
        else:
            print("Generating video (this usually takes 1-6 minutes)...")
        try:
            generate(
                prompt, path, model,
                image=start_image,
                references=references,
                aspect_ratio=args.aspect,
                resolution=args.resolution,
                duration=args.duration,
                negative_prompt=args.negative,
                timeout_s=args.timeout,
            )
        except BillingUnavailable as exc:
            print(f"BILLING_UNAVAILABLE: {exc}")
            print("The API cannot serve this request (quota exhausted or billing not enabled).")
            return EXIT_PAID_REQUIRED
        except GenerationError as exc:
            print(f"Error: {exc}")
            failures += 1

    if failures:
        print(f"\n{failures}/{len(jobs)} video(s) failed.")
        return EXIT_FAILED
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
