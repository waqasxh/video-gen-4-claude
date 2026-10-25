"""Unit tests for pure helpers in main.py (no network)."""
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import main  # noqa: E402
from google.genai import errors as genai_errors  # noqa: E402


def test_template_braces_are_preserved():
    template = 'A {subject} with config {"a": 1}'
    assert main.apply_style_template(template, "cat") == 'A cat with config {"a": 1}'


def test_template_without_placeholder_prepends_subject():
    assert main.apply_style_template("flat style", "cat") == "cat. flat style"


def test_load_style_template(tmp_path):
    style = tmp_path / "s.md"
    style.write_text("## Prompt Template\n\n```\nFilm [SUBJECT] café\n```\n", encoding="utf-8")
    assert main.load_style_template(style) == "Film {subject} café"


def test_load_style_template_missing_section(tmp_path):
    style = tmp_path / "s.md"
    style.write_text("nothing here", encoding="utf-8")
    with pytest.raises(ValueError):
        main.load_style_template(style)


@pytest.mark.parametrize(
    "code,status,message,expected",
    [
        (429, "RESOURCE_EXHAUSTED", "quota exceeded", True),
        (403, "PERMISSION_DENIED", "billing required", True),
        (400, "INVALID_ARGUMENT", "free tier not available, limit: 0", True),
        (400, "INVALID_ARGUMENT", "bad prompt", False),
        (500, "INTERNAL", "oops", False),
    ],
)
def test_is_quota_error(code, status, message, expected):
    exc = genai_errors.APIError(code, {"error": {"code": code, "status": status, "message": message}})
    assert main._is_quota_error(exc) is expected


@pytest.mark.parametrize(
    "duration,resolution,aspect,refs,expected_fragment",
    [
        (8, "720p", "16:9", 0, None),
        (4, "720p", "9:16", 0, None),
        (6, "1080p", "16:9", 0, "1080p"),
        (8, "1080p", "16:9", 0, None),
        (8, "720p", "16:9", 3, None),
        (8, "720p", "16:9", 4, "at most"),
        (6, "720p", "16:9", 1, "--duration 8"),
        (8, "720p", "9:16", 1, "16:9"),
    ],
)
def test_validate_options(duration, resolution, aspect, refs, expected_fragment):
    result = main.validate_options(duration, resolution, aspect, refs)
    if expected_fragment is None:
        assert result is None
    else:
        assert expected_fragment in result


def test_load_image_sets_mime_type(tmp_path):
    img = tmp_path / "a.jpg"
    img.write_bytes(b"\xff\xd8data")
    part = main._load_image(img)
    assert part.mime_type == "image/jpeg"
    assert part.image_bytes == b"\xff\xd8data"


def test_load_image_rejects_unknown_extension(tmp_path):
    bad = tmp_path / "a.gif"
    bad.write_bytes(b"GIF89a")
    with pytest.raises(ValueError):
        main._load_image(bad)


class _FakeOperations:
    def __init__(self, finish_after):
        self.calls = 0
        self.finish_after = finish_after

    def get(self, operation):
        self.calls += 1
        return SimpleNamespace(done=self.calls >= self.finish_after)


def test_wait_for_operation_polls_until_done():
    client = SimpleNamespace(operations=_FakeOperations(finish_after=3))
    sleeps = []
    result = main._wait_for_operation(
        client, SimpleNamespace(done=False), timeout_s=100, poll_s=5,
        sleep=sleeps.append, clock=lambda: 0.0,
    )
    assert result.done
    assert sleeps == [5, 5, 5]


def test_wait_for_operation_returns_immediately_when_done():
    client = SimpleNamespace(operations=_FakeOperations(finish_after=1))
    op = SimpleNamespace(done=True)
    assert main._wait_for_operation(client, op, sleep=lambda s: None) is op
    assert client.operations.calls == 0


def test_wait_for_operation_times_out():
    client = SimpleNamespace(operations=_FakeOperations(finish_after=10**9))
    ticks = iter(range(0, 1000, 10))
    with pytest.raises(main.GenerationError, match="Timed out"):
        main._wait_for_operation(
            client, SimpleNamespace(done=False), timeout_s=25, poll_s=1,
            sleep=lambda s: None, clock=lambda: float(next(ticks)),
        )
