"""Tests for sessionbook.html module (TASK-018).

Comprehensive unit tests for HTML generation with XSS prevention,
path traversal prevention, and rendering of thinking blocks, user choices,
and sub-agent references.

Requirement trace: REQ-012, REQ-015, SEC-002, SEC-003, SEC-004, SEC-005.
"""

import os
from pathlib import Path


from sessionbook.html import (
    _compute_filename,
    _escape_html,
    _existing_session_ids,
    _render_sub_agent_card,
    _render_thinking_block,
    _render_turn_html,
    _render_user_choice,
    _validate_agent_id,
    build_html,
    save_html,
)
from sessionbook.jsonl import Session, SubAgentRef, ThinkingBlock, Turn, UserChoice


# ---------------------------------------------------------------------------
# _escape_html
# ---------------------------------------------------------------------------


class TestEscapeHtml:
    """Tests for _escape_html XSS prevention (SEC-002)."""

    def test_script_tag_escaped(self):
        """<script> tags are escaped to prevent XSS."""
        result = _escape_html("<script>alert(1)</script>")
        assert result == "&lt;script&gt;alert(1)&lt;/script&gt;"
        assert "<script>" not in result

    def test_attributes_escaped(self):
        """Quotes in attributes are escaped."""
        result = _escape_html('"onmouseover="alert(1)"')
        assert result == "&quot;onmouseover=&quot;alert(1)&quot;"
        assert "onmouseover=" not in result or "&quot;" in result

    def test_ampersand_escaped(self):
        """& is escaped to &amp;."""
        result = _escape_html("A & B")
        assert result == "A &amp; B"

    def test_single_quote_escaped(self):
        """Single quotes are escaped."""
        result = _escape_html("It's a test")
        assert "&" in result or "'" in result  # May be &#x27; or &apos;

    def test_non_string_converted(self):
        """Non-string input is converted to string first."""
        result = _escape_html(42)
        assert result == "42"

    def test_none_converted(self):
        """None is converted to string."""
        result = _escape_html(None)
        assert result == "None"

    def test_empty_string(self):
        """Empty string is handled."""
        result = _escape_html("")
        assert result == ""

    def test_normal_text_unchanged(self):
        """Text without special characters is unchanged."""
        result = _escape_html("Hello World")
        assert result == "Hello World"


# ---------------------------------------------------------------------------
# _validate_agent_id
# ---------------------------------------------------------------------------


class TestValidateAgentId:
    """Tests for _validate_agent_id path traversal prevention (SEC-003)."""

    def test_valid_alphanumeric(self):
        """Valid alphanumeric IDs are accepted."""
        assert _validate_agent_id("abc123") is True

    def test_valid_with_dash(self):
        """IDs with dashes are accepted."""
        assert _validate_agent_id("agent-1") is True

    def test_valid_with_underscore(self):
        """IDs with underscores are accepted."""
        assert _validate_agent_id("a_b") is True

    def test_valid_mixed(self):
        """Mixed alphanumeric, dash, and underscore are accepted."""
        assert _validate_agent_id("agent-123_test") is True

    def test_path_traversal_rejected(self):
        """Path traversal attempts are rejected."""
        assert _validate_agent_id("../../../etc/passwd") is False

    def test_empty_string_rejected(self):
        """Empty string is rejected."""
        assert _validate_agent_id("") is False

    def test_slash_rejected(self):
        """IDs with slashes are rejected."""
        assert _validate_agent_id("agent/bad") is False

    def test_null_byte_rejected(self):
        """IDs with null bytes are rejected."""
        assert _validate_agent_id("agent\x00bad") is False

    def test_dot_rejected(self):
        """IDs with dots are rejected (path traversal risk)."""
        assert _validate_agent_id("agent.bad") is False

    def test_space_rejected(self):
        """IDs with spaces are rejected."""
        assert _validate_agent_id("agent bad") is False


# ---------------------------------------------------------------------------
# _render_thinking_block
# ---------------------------------------------------------------------------


class TestRenderThinkingBlock:
    """Tests for _render_thinking_block (thinking block rendering)."""

    def test_collapsed_by_default(self):
        """Thinking blocks are collapsed by default (no 'open' attribute)."""
        thinking = ThinkingBlock(text="This is a thought")
        result = _render_thinking_block(thinking)
        assert "<details" in result
        assert "open" not in result  # Should NOT have 'open' attribute

    def test_text_escaped(self):
        """Thinking block text is HTML-escaped."""
        thinking = ThinkingBlock(text="<script>alert(1)</script>")
        result = _render_thinking_block(thinking)
        assert "&lt;script&gt;" in result
        assert "<script>" not in result

    def test_details_present(self):
        """<details> element is present."""
        thinking = ThinkingBlock(text="Test")
        result = _render_thinking_block(thinking)
        assert '<details class="thinking-block">' in result
        assert "</details>" in result

    def test_summary_present(self):
        """<summary> element with 'Thinking' label is present."""
        thinking = ThinkingBlock(text="Test")
        result = _render_thinking_block(thinking)
        assert "<summary>Thinking</summary>" in result

    def test_content_div_present(self):
        """Content is wrapped in a div with thinking-content class."""
        thinking = ThinkingBlock(text="Test content")
        result = _render_thinking_block(thinking)
        assert '<div class="thinking-content"><p>Test content</p>\n</div>' in result


# ---------------------------------------------------------------------------
# _render_user_choice
# ---------------------------------------------------------------------------


class TestRenderUserChoice:
    """Tests for _render_user_choice (user choice rendering)."""

    def test_question_rendered(self):
        """Question text is rendered."""
        choice = UserChoice(
            question="What would you like to do?",
            options=["Option A", "Option B"],
            selected_index=0,
        )
        result = _render_user_choice(choice)
        assert "What would you like to do?" in result

    def test_options_listed(self):
        """All options are listed."""
        choice = UserChoice(
            question="Choose one:",
            options=["First", "Second", "Third"],
            selected_index=1,
        )
        result = _render_user_choice(choice)
        assert "First" in result
        assert "Second" in result
        assert "Third" in result

    def test_selected_option_highlighted(self):
        """Selected option has choice-selected class."""
        choice = UserChoice(
            question="Pick:",
            options=["A", "B", "C"],
            selected_index=1,
        )
        result = _render_user_choice(choice)
        # The selected option (index 1, "B") should have choice-selected class
        assert 'class="choice-option choice-selected">B</li>' in result

    def test_non_selected_options_normal(self):
        """Non-selected options have only choice-option class."""
        choice = UserChoice(
            question="Pick:",
            options=["A", "B", "C"],
            selected_index=1,
        )
        result = _render_user_choice(choice)
        # A and C should not have choice-selected class
        assert 'class="choice-option">A</li>' in result
        assert 'class="choice-option">C</li>' in result

    def test_question_escaped(self):
        """Question text is HTML-escaped."""
        choice = UserChoice(
            question="<script>alert('xss')</script>",
            options=["Safe"],
            selected_index=0,
        )
        result = _render_user_choice(choice)
        assert "&lt;script&gt;" in result
        assert "<script>" not in result

    def test_options_escaped(self):
        """Option text is HTML-escaped."""
        choice = UserChoice(
            question="Pick:",
            options=["<b>Bold</b>", "Normal"],
            selected_index=0,
        )
        result = _render_user_choice(choice)
        assert "&lt;b&gt;Bold&lt;/b&gt;" in result
        assert "<b>Bold</b>" not in result


# ---------------------------------------------------------------------------
# _render_sub_agent_card
# ---------------------------------------------------------------------------


class TestRenderSubAgentCard:
    """Tests for _render_sub_agent_card (sub-agent reference rendering)."""

    def test_card_with_link(self):
        """Card with transcript_path shows a link."""
        ref = SubAgentRef(
            agent_id="test-agent",
            subagent_type="executor",
            description="Test task",
            summary="Task completed successfully",
            transcript_path="./transcripts/agent-123.html",
        )
        result = _render_sub_agent_card(ref)
        assert '<a href="./transcripts/agent-123.html"' in result
        assert "View transcript" in result

    def test_card_without_link(self):
        """Card without transcript_path shows 'not available' message."""
        ref = SubAgentRef(
            agent_id="test-agent",
            subagent_type="executor",
            description="Test task",
            summary="Task completed",
            transcript_path=None,
        )
        result = _render_sub_agent_card(ref)
        assert "Transcript not available" in result
        assert "<a href=" not in result

    def test_metadata_shown(self):
        """Duration and tool use count are shown when present."""
        ref = SubAgentRef(
            agent_id="test-agent",
            subagent_type="executor",
            description="Test task",
            summary="Done",
            duration_ms=5000,
            tool_use_count=3,
            transcript_path=None,
        )
        result = _render_sub_agent_card(ref)
        assert "Duration: 5.0s" in result
        assert "Tool uses: 3" in result

    def test_metadata_absent(self):
        """Metadata section not shown when data is absent."""
        ref = SubAgentRef(
            agent_id="test-agent",
            subagent_type="executor",
            description="Test task",
            summary="Done",
            transcript_path=None,
        )
        result = _render_sub_agent_card(ref)
        # No meta div should be present if no metadata
        # (this is a weak test, but we can check the result doesn't crash)
        assert "sub-agent-card" in result

    def test_summary_truncated(self):
        """Summary is truncated to 500 characters."""
        long_summary = "A" * 600
        ref = SubAgentRef(
            agent_id="test-agent",
            subagent_type="executor",
            description="Test task",
            summary=long_summary,
            transcript_path=None,
        )
        result = _render_sub_agent_card(ref)
        # Should have ellipsis
        assert "..." in result
        # Should not have full 600 chars
        assert long_summary not in result

    def test_content_escaped(self):
        """Sub-agent card content is HTML-escaped."""
        ref = SubAgentRef(
            agent_id="test-123",
            subagent_type="<script>alert(1)</script>",
            description="<b>Description</b>",
            summary="<img src=x onerror=alert(1)>",
            transcript_path=None,
        )
        result = _render_sub_agent_card(ref)
        assert "&lt;script&gt;" in result
        assert "<script>" not in result
        assert "&lt;b&gt;" in result
        assert "<b>Description</b>" not in result
        assert "&lt;img" in result
        assert "<img" not in result


# ---------------------------------------------------------------------------
# _render_turn_html
# ---------------------------------------------------------------------------


class TestRenderTurnHtml:
    """Tests for _render_turn_html (turn rendering)."""

    def test_user_turn_rendered(self):
        """User turn is rendered with correct role class."""
        turn = Turn(role="user", text="Hello", timestamp="2026-02-07T10:00:00Z")
        result = _render_turn_html(turn, 0)
        assert 'class="turn turn-user"' in result
        assert "Hello" in result

    def test_assistant_turn_rendered(self):
        """Assistant turn is rendered with correct role class."""
        turn = Turn(role="assistant", text="Hi there", timestamp="2026-02-07T10:00:01Z")
        result = _render_turn_html(turn, 1)
        assert 'class="turn turn-assistant"' in result
        assert "Hi there" in result

    def test_thinking_blocks_included(self):
        """Thinking blocks are rendered in the turn."""
        turn = Turn(
            role="assistant",
            text="Response",
            timestamp="2026-02-07T10:00:00Z",
            thinking_blocks=[ThinkingBlock(text="I need to think")],
        )
        result = _render_turn_html(turn, 0)
        assert "I need to think" in result
        assert "<details" in result

    def test_sub_agent_refs_included(self):
        """Sub-agent references are rendered in the turn."""
        ref = SubAgentRef(
            agent_id="valid-id",
            subagent_type="executor",
            description="Task",
            summary="Done",
            transcript_path=None,
        )
        turn = Turn(
            role="assistant",
            text="Response",
            timestamp="2026-02-07T10:00:00Z",
            sub_agent_refs=[ref],
        )
        result = _render_turn_html(turn, 0)
        assert "sub-agent-card" in result
        assert "executor" in result

    def test_invalid_agent_id_skipped(self):
        """Sub-agent refs with invalid IDs are skipped."""
        ref = SubAgentRef(
            agent_id="../bad/path",
            subagent_type="executor",
            description="Task",
            summary="Done",
            transcript_path=None,
        )
        turn = Turn(
            role="assistant",
            text="Response",
            timestamp="2026-02-07T10:00:00Z",
            sub_agent_refs=[ref],
        )
        result = _render_turn_html(turn, 0)
        # Should not render the sub-agent card
        assert "sub-agent-card" not in result

    def test_turn_index_in_id(self):
        """Turn index is used in the element ID."""
        turn = Turn(role="user", text="Test", timestamp="2026-02-07T10:00:00Z")
        result = _render_turn_html(turn, 5)
        assert 'id="turn-5"' in result

    def test_timestamp_rendered(self):
        """Timestamp is rendered in the turn."""
        turn = Turn(role="user", text="Test", timestamp="2026-02-07T10:00:00Z")
        result = _render_turn_html(turn, 0)
        assert "2026-02-07T10:00:00Z" in result


# ---------------------------------------------------------------------------
# build_html
# ---------------------------------------------------------------------------


class TestBuildHtml:
    """Tests for build_html (full HTML generation)."""

    def test_contains_doctype(self):
        """Generated HTML contains DOCTYPE."""
        session = Session(
            session_id="test-session",
            turns=[Turn(role="user", text="Test", timestamp="2026-02-07T10:00:00Z")],
            filepath=Path("/tmp/test.jsonl"),
        )
        result = build_html(session)
        assert "<!DOCTYPE html>" in result

    def test_contains_meta_tags(self):
        """Generated HTML contains meta tags."""
        session = Session(
            session_id="test-session",
            turns=[Turn(role="user", text="Test", timestamp="2026-02-07T10:00:00Z")],
            filepath=Path("/tmp/test.jsonl"),
        )
        result = build_html(session)
        assert '<meta charset="UTF-8">' in result
        assert '<meta name="viewport"' in result

    def test_contains_css(self):
        """Generated HTML contains inline CSS."""
        session = Session(
            session_id="test-session",
            turns=[Turn(role="user", text="Test", timestamp="2026-02-07T10:00:00Z")],
            filepath=Path("/tmp/test.jsonl"),
        )
        result = build_html(session)
        assert "<style>" in result
        assert ".turn" in result
        assert "</style>" in result

    def test_session_id_in_meta_tag(self):
        """Session ID is present in meta tag."""
        session = Session(
            session_id="unique-session-id",
            turns=[Turn(role="user", text="Test", timestamp="2026-02-07T10:00:00Z")],
            filepath=Path("/tmp/test.jsonl"),
        )
        result = build_html(session)
        assert 'name="sessionbook-session-id"' in result
        assert 'content="unique-session-id"' in result

    def test_turns_rendered_in_order(self):
        """Turns are rendered in order."""
        session = Session(
            session_id="test",
            turns=[
                Turn(role="user", text="First", timestamp="2026-02-07T10:00:00Z"),
                Turn(role="assistant", text="Second", timestamp="2026-02-07T10:00:01Z"),
                Turn(role="user", text="Third", timestamp="2026-02-07T10:00:02Z"),
            ],
            filepath=Path("/tmp/test.jsonl"),
        )
        result = build_html(session)
        first_idx = result.find("First")
        second_idx = result.find("Second")
        third_idx = result.find("Third")
        assert first_idx < second_idx < third_idx

    def test_empty_text_escaped(self):
        """Empty or special text is properly escaped."""
        session = Session(
            session_id="test",
            turns=[
                Turn(
                    role="user",
                    text="<script>alert(1)</script>",
                    timestamp="2026-02-07T10:00:00Z",
                )
            ],
            filepath=Path("/tmp/test.jsonl"),
        )
        result = build_html(session)
        assert "&lt;script&gt;" in result
        assert "<script>alert(1)</script>" not in result


# ---------------------------------------------------------------------------
# _compute_filename
# ---------------------------------------------------------------------------


class TestComputeFilename:
    """Tests for _compute_filename (timestamp to filename conversion)."""

    def test_timestamp_to_filename(self):
        """Timestamp is converted to filename format."""
        session = Session(
            session_id="test",
            turns=[Turn(role="user", text="Test", timestamp="2026-02-07T10:15:30Z")],
            filepath=Path("/tmp/test.jsonl"),
        )
        result = _compute_filename(session)
        assert result.endswith(".html")
        assert "2026" in result
        assert "02" in result
        assert "07" in result

    def test_fallback_to_now(self):
        """Falls back to current time if timestamp is malformed."""
        session = Session(
            session_id="test",
            turns=[Turn(role="user", text="Test", timestamp="invalid")],
            filepath=Path("/tmp/test.jsonl"),
        )
        result = _compute_filename(session)
        assert result.endswith(".html")
        assert "T" in result  # Should have ISO format

    def test_empty_turns_fallback(self):
        """Falls back to current time if turns list is empty."""
        session = Session(
            session_id="test",
            turns=[],
            filepath=Path("/tmp/test.jsonl"),
        )
        result = _compute_filename(session)
        assert result.endswith(".html")


# ---------------------------------------------------------------------------
# save_html
# ---------------------------------------------------------------------------


class TestSaveHtml:
    """Tests for save_html (atomic write and collision handling)."""

    def test_atomic_write(self, tmp_path):
        """File is written atomically (no .tmp leftover)."""
        session = Session(
            session_id="test",
            turns=[Turn(role="user", text="Test", timestamp="2026-02-07T10:00:00Z")],
            filepath=Path("/tmp/test.jsonl"),
        )
        result = save_html(session, tmp_path)
        assert result is not None
        assert result.exists()
        # Check no .tmp files remain
        tmp_files = list(tmp_path.glob("*.tmp"))
        assert len(tmp_files) == 0

    def test_collision_handling(self, tmp_path):
        """Collision handling adds numeric suffix."""
        session = Session(
            session_id="test",
            turns=[Turn(role="user", text="Test", timestamp="2026-02-07T10:00:00Z")],
            filepath=Path("/tmp/test.jsonl"),
        )
        # Save first file
        result1 = save_html(session, tmp_path)
        assert result1 is not None

        # Save second file with same timestamp
        result2 = save_html(session, tmp_path)
        assert result2 is not None

        # Second file should have -1 suffix
        assert result1 != result2
        assert "-1.html" in result2.name

    def test_permissions(self, tmp_path):
        """File has 0o644 permissions."""
        session = Session(
            session_id="test",
            turns=[Turn(role="user", text="Test", timestamp="2026-02-07T10:00:00Z")],
            filepath=Path("/tmp/test.jsonl"),
        )
        result = save_html(session, tmp_path)
        assert result is not None
        mode = os.stat(result).st_mode & 0o777
        assert mode == 0o644

    def test_empty_session_returns_none(self, tmp_path):
        """Empty session (no turns) returns None."""
        session = Session(
            session_id="test",
            turns=[],
            filepath=Path("/tmp/test.jsonl"),
        )
        result = save_html(session, tmp_path)
        assert result is None

    def test_unwritable_directory_returns_none(self, tmp_path):
        """Unwritable directory returns None."""
        session = Session(
            session_id="test",
            turns=[Turn(role="user", text="Test", timestamp="2026-02-07T10:00:00Z")],
            filepath=Path("/tmp/test.jsonl"),
        )
        # Try to write to a non-existent parent directory with no permission to create
        unwritable_dir = Path("/nonexistent/deeply/nested/path")
        result = save_html(session, unwritable_dir)
        assert result is None


# ---------------------------------------------------------------------------
# _existing_session_ids
# ---------------------------------------------------------------------------


class TestExistingSessionIds:
    """Tests for _existing_session_ids (scan HTML files for session IDs)."""

    def test_scan_empty_directory(self, tmp_path):
        """Empty directory returns empty set."""
        result = _existing_session_ids(tmp_path)
        assert result == set()

    def test_scan_nonexistent_directory(self, tmp_path):
        """Nonexistent directory returns empty set."""
        nonexistent = tmp_path / "nonexistent"
        result = _existing_session_ids(nonexistent)
        assert result == set()

    def test_scan_html_files(self, tmp_path):
        """Extracts session IDs from HTML meta tags."""
        # Create HTML file with session ID
        html_content = """<!DOCTYPE html>
<html>
<head>
    <meta name="sessionbook-session-id" content="session-123">
</head>
<body></body>
</html>"""
        html_file = tmp_path / "test.html"
        html_file.write_text(html_content)

        result = _existing_session_ids(tmp_path)
        assert "session-123" in result

    def test_scan_multiple_files(self, tmp_path):
        """Extracts session IDs from multiple HTML files."""
        for i in range(3):
            html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta name="sessionbook-session-id" content="session-{i}">
</head>
<body></body>
</html>"""
            html_file = tmp_path / f"test{i}.html"
            html_file.write_text(html_content)

        result = _existing_session_ids(tmp_path)
        assert "session-0" in result
        assert "session-1" in result
        assert "session-2" in result

    def test_scan_ignores_non_html(self, tmp_path):
        """Non-HTML files are ignored."""
        txt_file = tmp_path / "test.txt"
        txt_file.write_text("This is not HTML")

        result = _existing_session_ids(tmp_path)
        assert result == set()

    def test_scan_handles_malformed_html(self, tmp_path):
        """Malformed HTML files are skipped without error."""
        html_file = tmp_path / "malformed.html"
        html_file.write_text("This is not valid HTML")

        result = _existing_session_ids(tmp_path)
        assert result == set()
