"""Benchmarks and edge-case tests for the sessionbook conversion pipeline (TASK-022, TASK-023).

Covers:
- Large session performance (gated behind sessionbook_BENCH=1)
- Malformed JSONL resilience (50% invalid lines)
- Timestamp edge cases for _compute_filename
- Very long path for encode_project_path
- Whitespace-only content sessions
- Large single turn (100KB)
"""

import json
import os
import time
from pathlib import Path

import pytest

from sessionbook.jsonl import Turn, Session, parse_session, encode_project_path
from sessionbook.html import build_html, save_html, _compute_filename


# ---------------------------------------------------------------------------
# Helper: write a JSONL file with N user/assistant turn pairs
# ---------------------------------------------------------------------------


def _make_jsonl_lines(n_turns: int) -> str:
    """Generate n_turns alternating user/assistant JSONL lines."""
    lines = []
    for i in range(n_turns):
        if i % 2 == 0:
            entry = {
                "type": "user",
                "sessionId": "bench-session",
                "timestamp": f"2026-02-07T10:00:{i:02d}Z",
                "message": {"role": "user", "content": f"User message {i}"},
            }
        else:
            entry = {
                "type": "assistant",
                "sessionId": "bench-session",
                "timestamp": f"2026-02-07T10:00:{i:02d}Z",
                "requestId": f"req-{i}",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": f"Assistant response {i}"}],
                },
            }
        lines.append(json.dumps(entry))
    return "\n".join(lines) + "\n"


# ===========================================================================
# 1. Large session benchmark (gated behind sessionbook_BENCH=1)
# ===========================================================================


@pytest.mark.skipif(
    os.environ.get("sessionbook_BENCH") != "1",
    reason="Set sessionbook_BENCH=1 to run benchmarks",
)
class TestLargeSessionBenchmark:
    """Performance benchmarks for 1000-turn sessions."""

    @pytest.fixture()
    def large_jsonl(self, tmp_path):
        """Create a 1000-turn JSONL file in a temp directory."""
        filepath = tmp_path / "large_session.jsonl"
        filepath.write_text(_make_jsonl_lines(1000))
        return filepath

    def test_parse_session_under_2_seconds(self, large_jsonl):
        start = time.monotonic()
        session = parse_session(large_jsonl)
        elapsed = time.monotonic() - start

        assert session is not None
        assert len(session.turns) == 1000
        assert elapsed < 2.0, f"parse_session took {elapsed:.3f}s, expected < 2.0s"

    def test_full_pipeline_reasonable_time(self, large_jsonl, tmp_path):
        """Parse + build_html + save should complete in reasonable time."""
        output_dir = tmp_path / "output"

        start = time.monotonic()
        session = parse_session(large_jsonl)
        assert session is not None
        result = save_html(session, output_dir)
        elapsed = time.monotonic() - start

        assert result is not None
        assert result.exists()
        assert result.suffix == ".html"
        # Allow generous 10s for full pipeline including disk I/O
        assert elapsed < 10.0, f"Full pipeline took {elapsed:.3f}s, expected < 10.0s"


# ===========================================================================
# 2. 50% malformed JSONL resilience
# ===========================================================================


class TestHalfMalformedJsonl:
    """Every other line is invalid JSON; valid lines should still parse."""

    @pytest.fixture()
    def half_malformed_jsonl(self, tmp_path):
        filepath = tmp_path / "half_malformed.jsonl"
        lines = []
        valid_count = 0
        for i in range(20):
            if i % 2 == 0:
                # Valid line
                if valid_count % 2 == 0:
                    entry = {
                        "type": "user",
                        "sessionId": "malformed-sess",
                        "timestamp": f"2026-02-07T10:00:{valid_count:02d}Z",
                        "message": {
                            "role": "user",
                            "content": f"Valid user message {valid_count}",
                        },
                    }
                else:
                    entry = {
                        "type": "assistant",
                        "sessionId": "malformed-sess",
                        "timestamp": f"2026-02-07T10:00:{valid_count:02d}Z",
                        "requestId": f"req-{valid_count}",
                        "message": {
                            "role": "assistant",
                            "content": [
                                {
                                    "type": "text",
                                    "text": f"Valid assistant response {valid_count}",
                                }
                            ],
                        },
                    }
                lines.append(json.dumps(entry))
                valid_count += 1
            else:
                # Invalid JSON line
                lines.append(f"{{{{this is not valid json line {i}")
        filepath.write_text("\n".join(lines) + "\n")
        return filepath, valid_count

    def test_valid_turns_extracted(self, half_malformed_jsonl):
        filepath, valid_count = half_malformed_jsonl
        session = parse_session(filepath)

        assert session is not None
        assert session.session_id == "malformed-sess"
        # 10 valid lines: 5 user + 5 assistant = 10 turns
        assert len(session.turns) == valid_count

    def test_roles_correct(self, half_malformed_jsonl):
        filepath, _ = half_malformed_jsonl
        session = parse_session(filepath)

        assert session is not None
        roles = [t.role for t in session.turns]
        expected = ["user", "assistant"] * 5
        assert roles == expected

    def test_content_intact(self, half_malformed_jsonl):
        filepath, _ = half_malformed_jsonl
        session = parse_session(filepath)

        assert session is not None
        user_turns = [t for t in session.turns if t.role == "user"]
        for i, turn in enumerate(user_turns):
            idx = i * 2  # user messages are at even valid_count indices
            assert turn.text == f"Valid user message {idx}"


# ===========================================================================
# 3. Timestamp edge cases for compute_filename
# ===========================================================================


class TestComputeFilenameEdgeCases:
    """Timestamp variants that _compute_filename must handle without crashing."""

    def _session_with_timestamp(self, ts: str) -> Session:
        return Session(
            session_id="ts-test",
            turns=[Turn(role="user", text="X", timestamp=ts)],
            filepath=Path("/tmp/test.jsonl"),
        )

    def test_timestamp_without_timezone(self):
        """Naive ISO timestamp (no tz info)."""
        session = self._session_with_timestamp("2026-02-07T10:00:00")
        filename = _compute_filename(session)
        assert filename.endswith(".html")
        assert "2026" in filename

    def test_timestamp_with_z_suffix(self):
        """UTC timestamp with Z suffix."""
        session = self._session_with_timestamp("2026-02-07T10:00:00Z")
        filename = _compute_filename(session)
        assert filename.endswith(".html")
        assert "2026" in filename

    def test_timestamp_with_offset(self):
        """Timestamp with explicit UTC offset."""
        session = self._session_with_timestamp("2026-02-07T10:00:00+05:30")
        filename = _compute_filename(session)
        assert filename.endswith(".html")
        assert "2026" in filename

    def test_empty_timestamp(self):
        """Empty string timestamp falls back to now()."""
        session = self._session_with_timestamp("")
        filename = _compute_filename(session)
        assert filename.endswith(".html")
        # Should have ISO-like format with T separator
        assert "T" in filename

    def test_garbage_timestamp(self):
        """Non-parseable timestamp falls back to now()."""
        session = self._session_with_timestamp("not-a-timestamp")
        filename = _compute_filename(session)
        assert filename.endswith(".html")
        assert "T" in filename


# ===========================================================================
# 4. Very long path for encode_project_path
# ===========================================================================


class TestEncodeProjectPathLong:
    """encode_project_path with a 500-character path."""

    def test_long_path(self):
        # Build a 500-char absolute path: /aaa.../aaa
        segments = []
        total = 0
        while total < 499:
            seg = "a" * min(50, 499 - total)
            segments.append(seg)
            total += len(seg) + 1  # +1 for the separator
        long_path = "/" + "/".join(segments)
        assert len(long_path) >= 500

        result = encode_project_path(Path(long_path))

        # Should replace all / with -
        assert "/" not in result
        assert result.startswith("-")
        assert len(result) == len(long_path)

    def test_long_path_roundtrip_slashes(self):
        """Every slash is replaced; character count is preserved."""
        path_str = "/" + "/".join(["segment"] * 100)
        result = encode_project_path(Path(path_str))
        assert result.count("-") == path_str.count("/")


# ===========================================================================
# 5. Session with only whitespace content
# ===========================================================================


class TestWhitespaceOnlyContent:
    """User/assistant turns where content is all whitespace."""

    def test_whitespace_user_returns_none(self, tmp_path):
        """A session with only whitespace user content produces no turns."""
        filepath = tmp_path / "whitespace.jsonl"
        entry = {
            "type": "user",
            "sessionId": "ws-sess",
            "timestamp": "2026-02-07T10:00:00Z",
            "message": {"role": "user", "content": "   \n\t  "},
        }
        filepath.write_text(json.dumps(entry) + "\n")
        session = parse_session(filepath)
        # parse_session returns None when no extractable turns
        assert session is None

    def test_whitespace_assistant_returns_none(self, tmp_path):
        """An assistant turn with only whitespace text in content blocks."""
        filepath = tmp_path / "ws_assistant.jsonl"
        entry = {
            "type": "assistant",
            "sessionId": "ws-sess",
            "timestamp": "2026-02-07T10:00:00Z",
            "requestId": "req-ws",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": "   \n\t  "}],
            },
        }
        filepath.write_text(json.dumps(entry) + "\n")
        session = parse_session(filepath)
        # The text "   \n\t  " is non-empty but the collapsed result with
        # strip() is empty, so _flush_assistant skips it -> returns None
        assert session is None

    def test_mixed_whitespace_and_real_content(self, tmp_path):
        """Whitespace-only entries are skipped; real entries are kept."""
        filepath = tmp_path / "mixed_ws.jsonl"
        lines = [
            json.dumps(
                {
                    "type": "user",
                    "sessionId": "ws-sess",
                    "timestamp": "2026-02-07T10:00:00Z",
                    "message": {"role": "user", "content": "   "},
                }
            ),
            json.dumps(
                {
                    "type": "user",
                    "sessionId": "ws-sess",
                    "timestamp": "2026-02-07T10:00:01Z",
                    "message": {"role": "user", "content": "Real question"},
                }
            ),
            json.dumps(
                {
                    "type": "assistant",
                    "sessionId": "ws-sess",
                    "timestamp": "2026-02-07T10:00:02Z",
                    "requestId": "req-1",
                    "message": {
                        "role": "assistant",
                        "content": [{"type": "text", "text": "Real answer"}],
                    },
                }
            ),
        ]
        filepath.write_text("\n".join(lines) + "\n")
        session = parse_session(filepath)
        assert session is not None
        assert len(session.turns) == 2
        assert session.turns[0].text == "Real question"
        assert session.turns[1].text == "Real answer"


# ===========================================================================
# 6. Large single turn (100KB of text)
# ===========================================================================


class TestLargeSingleTurn:
    """A single assistant turn with 100KB of text."""

    @pytest.fixture()
    def large_turn_jsonl(self, tmp_path):
        filepath = tmp_path / "large_turn.jsonl"
        large_text = "A" * (100 * 1024)  # 100KB
        lines = [
            json.dumps(
                {
                    "type": "user",
                    "sessionId": "large-sess",
                    "timestamp": "2026-02-07T10:00:00Z",
                    "message": {"role": "user", "content": "Generate a lot of text"},
                }
            ),
            json.dumps(
                {
                    "type": "assistant",
                    "sessionId": "large-sess",
                    "timestamp": "2026-02-07T10:00:01Z",
                    "requestId": "req-large",
                    "message": {
                        "role": "assistant",
                        "content": [{"type": "text", "text": large_text}],
                    },
                }
            ),
        ]
        filepath.write_text("\n".join(lines) + "\n")
        return filepath, large_text

    def test_parse_does_not_crash(self, large_turn_jsonl):
        filepath, large_text = large_turn_jsonl
        session = parse_session(filepath)
        assert session is not None
        assert len(session.turns) == 2

    def test_text_preserved(self, large_turn_jsonl):
        filepath, large_text = large_turn_jsonl
        session = parse_session(filepath)
        assert session is not None
        assistant_turn = [t for t in session.turns if t.role == "assistant"][0]
        assert len(assistant_turn.text) == len(large_text)
        assert assistant_turn.text == large_text

    def test_html_valid(self, large_turn_jsonl, tmp_path):
        filepath, _ = large_turn_jsonl
        session = parse_session(filepath)
        assert session is not None
        html = build_html(session)
        assert "<!DOCTYPE html>" in html
        # Verify the HTML contains the large text
        assert len(html) > 100 * 1024

    def test_save_html_large_turn(self, large_turn_jsonl, tmp_path):
        filepath, _ = large_turn_jsonl
        session = parse_session(filepath)
        assert session is not None
        output_dir = tmp_path / "output"
        result = save_html(session, output_dir)
        assert result is not None
        assert result.exists()
        # Verify the saved file is valid HTML
        html_content = result.read_text()
        assert "<!DOCTYPE html>" in html_content
        assert 'name="sessionbook-session-id"' in html_content
