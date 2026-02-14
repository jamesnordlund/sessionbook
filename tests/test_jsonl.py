"""Tests for sessionbook.jsonl module (TASK-006).

Requirement trace: REQ-017, REQ-018, REQ-019, REQ-020, DI-002, DI-003,
ERR-003, ERR-004, ERR-006.
"""

import os
import time
from pathlib import Path
from unittest import mock

import pytest

from sessionbook.jsonl import (
    Session,
    Turn,
    _extract_text,
    discover_sessions,
    encode_project_path,
    parse_session,
)

FIXTURES = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# encode_project_path
# ---------------------------------------------------------------------------


class TestEncodeProjectPath:
    """Tests for encode_project_path (REQ-017)."""

    def test_typical_path(self):
        result = encode_project_path(Path("/Users/james/foo"))
        assert result == "-Users-james-foo"

    def test_root_path(self):
        result = encode_project_path(Path("/"))
        assert result == "-"

    def test_home_dir(self):
        result = encode_project_path(Path("/Users/james"))
        assert result == "-Users-james"

    def test_path_with_spaces(self):
        result = encode_project_path(Path("/Users/james/my project"))
        assert result == "-Users-james-my project"

    def test_deeply_nested_path(self):
        result = encode_project_path(Path("/a/b/c/d/e"))
        assert result == "-a-b-c-d-e"


# ---------------------------------------------------------------------------
# parse_session -- simple_session.jsonl
# ---------------------------------------------------------------------------


class TestParseSimpleSession:
    """Tests for parse_session with a simple 4-turn conversation (REQ-018)."""

    @pytest.fixture()
    def session(self):
        return parse_session(FIXTURES / "simple_session.jsonl")

    def test_returns_session(self, session):
        assert session is not None
        assert isinstance(session, Session)

    def test_session_id(self, session):
        assert session.session_id == "sess-simple"

    def test_four_turns(self, session):
        assert len(session.turns) == 4

    def test_roles_alternate(self, session):
        roles = [t.role for t in session.turns]
        assert roles == ["user", "assistant", "user", "assistant"]

    def test_user_text_content(self, session):
        assert session.turns[0].text == "Hello, how are you?"
        assert session.turns[2].text == "What can you help me with?"

    def test_assistant_text_content(self, session):
        assert session.turns[1].text == "I am doing well, thank you!"
        assert (
            session.turns[3].text
            == "I can help with many things including coding and writing."
        )

    def test_timestamps_present(self, session):
        for turn in session.turns:
            assert turn.timestamp != ""
            assert "2026-02-07" in turn.timestamp

    def test_timestamp_ordering(self, session):
        timestamps = [t.timestamp for t in session.turns]
        assert timestamps == sorted(timestamps)

    def test_filepath(self, session):
        assert session.filepath == FIXTURES / "simple_session.jsonl"


# ---------------------------------------------------------------------------
# parse_session -- tool_use_session.jsonl
# ---------------------------------------------------------------------------


class TestParseToolUseSession:
    """Tests for parse_session with tool_use, tool_result, and thinking blocks (REQ-019)."""

    @pytest.fixture()
    def session(self):
        return parse_session(FIXTURES / "tool_use_session.jsonl")

    def test_returns_session(self, session):
        assert session is not None

    def test_tool_use_excluded_from_text(self, session):
        for turn in session.turns:
            assert "read_file" not in turn.text
            assert "list_files" not in turn.text

    def test_thinking_excluded_from_text(self, session):
        for turn in session.turns:
            assert "I should read the file" not in turn.text

    def test_text_blocks_extracted(self, session):
        # The first assistant turn should have text from the text block only
        assistant_turns = [t for t in session.turns if t.role == "assistant"]
        assert len(assistant_turns) >= 1
        assert "Let me read that file for you." in assistant_turns[0].text

    def test_tool_result_user_entry_skipped(self, session):
        """User entries with list content (tool_result arrays) are skipped."""
        user_turns = [t for t in session.turns if t.role == "user"]
        for ut in user_turns:
            # Only string-content user entries should be present
            assert isinstance(ut.text, str)
            assert ut.text.strip() != ""

    def test_user_string_content_kept(self, session):
        user_turns = [t for t in session.turns if t.role == "user"]
        texts = [t.text for t in user_turns]
        assert "Read the file README.md" in texts
        assert "Thanks, that is all I needed." in texts

    def test_assistant_count(self, session):
        # Consecutive assistant responses (separated only by tool_results, which are skipped)
        # are combined into one turn to match the sessionbook aesthetic.
        # In this session: assistant responses to user messages 1 and 2 are separate because
        # user message 2 ("Thanks...") is a real user input.
        assistant_turns = [t for t in session.turns if t.role == "assistant"]
        assert len(assistant_turns) == 2


# ---------------------------------------------------------------------------
# parse_session -- malformed.jsonl
# ---------------------------------------------------------------------------


class TestParseMalformed:
    """Tests for parse_session with malformed JSONL input (ERR-003, ERR-004)."""

    @pytest.fixture()
    def session(self):
        return parse_session(FIXTURES / "malformed.jsonl")

    def test_no_crash(self, session):
        """Parsing malformed file does not raise."""
        assert session is not None

    def test_valid_turns_parsed(self, session):
        assert len(session.turns) == 2

    def test_valid_content_preserved(self, session):
        assert session.turns[0].text == "First valid line"
        assert session.turns[1].text == "Second valid line"

    def test_roles(self, session):
        assert session.turns[0].role == "user"
        assert session.turns[1].role == "assistant"


# ---------------------------------------------------------------------------
# parse_session -- empty.jsonl
# ---------------------------------------------------------------------------


class TestParseEmpty:
    """Tests for parse_session with an empty file (ERR-006)."""

    def test_returns_none(self):
        result = parse_session(FIXTURES / "empty.jsonl")
        assert result is None


# ---------------------------------------------------------------------------
# parse_session -- unicode_session.jsonl
# ---------------------------------------------------------------------------


class TestParseUnicode:
    """Tests for parse_session with unicode content (REQ-020)."""

    @pytest.fixture()
    def session(self):
        return parse_session(FIXTURES / "unicode_session.jsonl")

    def test_returns_session(self, session):
        assert session is not None

    def test_cjk_preserved(self, session):
        assistant_turns = [t for t in session.turns if t.role == "assistant"]
        assert "\u4f60\u597d\u4e16\u754c" in assistant_turns[0].text

    def test_emoji_preserved(self, session):
        user_turns = [t for t in session.turns if t.role == "user"]
        # The second user entry has an emoji
        texts = " ".join(t.text for t in user_turns)
        assert "\U0001f389" in texts

    def test_accented_characters_preserved(self, session):
        assistant_turns = [t for t in session.turns if t.role == "assistant"]
        last_assistant = assistant_turns[-1].text
        assert "caf\u00e9" in last_assistant
        assert "r\u00e9sum\u00e9" in last_assistant

    def test_four_turns(self, session):
        assert len(session.turns) == 4


# ---------------------------------------------------------------------------
# parse_session -- requestid_collapse.jsonl
# ---------------------------------------------------------------------------


class TestRequestIdCollapsing:
    """Tests for requestId collapsing behavior (DI-003)."""

    @pytest.fixture()
    def session(self):
        return parse_session(FIXTURES / "requestid_collapse.jsonl")

    def test_returns_session(self, session):
        assert session is not None

    def test_assistant_turns_collapsed(self, session):
        """Three assistant entries with req-1 collapse into one turn;
        two with req-2 collapse into one turn. Total: 2 assistant turns."""
        assistant_turns = [t for t in session.turns if t.role == "assistant"]
        assert len(assistant_turns) == 2

    def test_user_turns_preserved(self, session):
        user_turns = [t for t in session.turns if t.role == "user"]
        assert len(user_turns) == 2

    def test_total_turns(self, session):
        assert len(session.turns) == 4

    def test_collapsed_text_joined(self, session):
        assistant_turns = [t for t in session.turns if t.role == "assistant"]
        # First collapsed group: three texts concatenated (streaming chunks)
        first = assistant_turns[0].text
        assert "Decorators are a way to modify functions." in first
        assert "They use the @syntax above a function definition." in first
        assert "Here is an example:" in first
        expected = (
            "Decorators are a way to modify functions."
            "They use the @syntax above a function definition."
            "Here is an example:"
        )
        assert first == expected

    def test_second_collapsed_group(self, session):
        assistant_turns = [t for t in session.turns if t.role == "assistant"]
        second = assistant_turns[1].text
        assert "A common use case is logging." in second
        assert "Another is authentication checks." in second
        expected = "A common use case is logging.Another is authentication checks."
        assert second == expected

    def test_turn_ordering(self, session):
        roles = [t.role for t in session.turns]
        assert roles == ["user", "assistant", "user", "assistant"]

    def test_first_timestamp_used(self, session):
        """The timestamp of the first entry in a collapsed group is used."""
        assistant_turns = [t for t in session.turns if t.role == "assistant"]
        assert assistant_turns[0].timestamp == "2026-02-07T14:00:01Z"
        assert assistant_turns[1].timestamp == "2026-02-07T14:00:05Z"


# ---------------------------------------------------------------------------
# discover_sessions -- nonexistent directory
# ---------------------------------------------------------------------------


class TestDiscoverSessionsNonexistent:
    """Tests for discover_sessions with nonexistent directory."""

    def test_returns_empty_list(self):
        result = discover_sessions(Path("/nonexistent"), 0)
        assert result == []


# ---------------------------------------------------------------------------
# discover_sessions -- mtime filter
# ---------------------------------------------------------------------------


class TestDiscoverSessionsMtimeFilter:
    """Tests for discover_sessions mtime filtering (REQ-018)."""

    def test_filters_by_mtime(self, tmp_path):
        """Files older than start_time are excluded from results."""
        # Create a project directory structure under a mocked CLAUDE_DIR
        project_dir = tmp_path / ".claude" / "projects" / "test-project"
        project_dir.mkdir(parents=True)

        # Create an "old" JSONL file
        old_file = project_dir / "old_session.jsonl"
        old_file.write_text(
            '{"type": "user", "sessionId": "old", "timestamp": "2026-01-01T00:00:00Z", '
            '"message": {"role": "user", "content": "old message"}}\n'
        )
        # Set mtime to a known past time
        old_mtime = time.time() - 3600  # 1 hour ago
        os.utime(old_file, (old_mtime, old_mtime))

        # Create a "new" JSONL file
        new_file = project_dir / "new_session.jsonl"
        new_file.write_text(
            '{"type": "user", "sessionId": "new", "timestamp": "2026-02-07T00:00:00Z", '
            '"message": {"role": "user", "content": "new message"}}\n'
        )
        # Set mtime to now
        new_mtime = time.time()
        os.utime(new_file, (new_mtime, new_mtime))

        # Patch CLAUDE_DIR so the security check passes
        mock_claude_dir = tmp_path / ".claude" / "projects"
        with mock.patch("sessionbook.jsonl.CLAUDE_DIR", mock_claude_dir):
            # Use start_time between old and new file mtimes
            start_time = old_mtime + 1
            sessions = discover_sessions(project_dir, start_time)

        assert len(sessions) == 1
        assert sessions[0].session_id == "new"

    def test_start_time_zero_returns_all(self, tmp_path):
        """start_time=0 returns all sessions."""
        project_dir = tmp_path / ".claude" / "projects" / "test-project"
        project_dir.mkdir(parents=True)

        f1 = project_dir / "s1.jsonl"
        f1.write_text(
            '{"type": "user", "sessionId": "s1", "timestamp": "2026-01-01T00:00:00Z", '
            '"message": {"role": "user", "content": "msg1"}}\n'
        )
        f2 = project_dir / "s2.jsonl"
        f2.write_text(
            '{"type": "user", "sessionId": "s2", "timestamp": "2026-01-02T00:00:00Z", '
            '"message": {"role": "user", "content": "msg2"}}\n'
        )

        mock_claude_dir = tmp_path / ".claude" / "projects"
        with mock.patch("sessionbook.jsonl.CLAUDE_DIR", mock_claude_dir):
            sessions = discover_sessions(project_dir, 0)

        assert len(sessions) == 2

    def test_security_check_rejects_outside_claude_dir(self, tmp_path):
        """discover_sessions rejects directories outside CLAUDE_DIR (SEC-006)."""
        outside_dir = tmp_path / "not_claude"
        outside_dir.mkdir()
        f = outside_dir / "session.jsonl"
        f.write_text(
            '{"type": "user", "sessionId": "x", "timestamp": "t", '
            '"message": {"role": "user", "content": "msg"}}\n'
        )

        # Do NOT patch CLAUDE_DIR -- the real CLAUDE_DIR won't match tmp_path
        sessions = discover_sessions(outside_dir, 0)
        assert sessions == []


# ---------------------------------------------------------------------------
# Entry filtering: isMeta, isSidechain, unknown type
# ---------------------------------------------------------------------------


class TestEntryFiltering:
    """Tests for JSONL entry filtering logic (DI-002)."""

    def test_isMeta_filtered(self, tmp_path):
        """Entries with isMeta: true are skipped."""
        f = tmp_path / "meta.jsonl"
        f.write_text(
            '{"type": "user", "sessionId": "s", "timestamp": "t", "isMeta": true, '
            '"message": {"role": "user", "content": "meta content"}}\n'
            '{"type": "user", "sessionId": "s", "timestamp": "t", '
            '"message": {"role": "user", "content": "real content"}}\n'
        )
        session = parse_session(f)
        assert session is not None
        assert len(session.turns) == 1
        assert session.turns[0].text == "real content"

    def test_isSidechain_filtered(self, tmp_path):
        """Entries with isSidechain: true are skipped."""
        f = tmp_path / "sidechain.jsonl"
        f.write_text(
            '{"type": "assistant", "sessionId": "s", "timestamp": "t", "isSidechain": true, '
            '"requestId": "r1", '
            '"message": {"role": "assistant", "content": [{"type": "text", "text": "side"}]}}\n'
            '{"type": "user", "sessionId": "s", "timestamp": "t", '
            '"message": {"role": "user", "content": "main content"}}\n'
        )
        session = parse_session(f)
        assert session is not None
        assert len(session.turns) == 1
        assert session.turns[0].role == "user"
        assert session.turns[0].text == "main content"

    def test_unknown_type_filtered(self, tmp_path):
        """Entries with type other than 'user'/'assistant' are skipped."""
        f = tmp_path / "unknown_type.jsonl"
        f.write_text(
            '{"type": "summary", "sessionId": "s", "timestamp": "t", '
            '"message": {"role": "user", "content": "summary content"}}\n'
            '{"type": "user", "sessionId": "s", "timestamp": "t", '
            '"message": {"role": "user", "content": "real content"}}\n'
        )
        session = parse_session(f)
        assert session is not None
        assert len(session.turns) == 1
        assert session.turns[0].text == "real content"

    def test_unknown_fields_tolerated(self, tmp_path):
        """Entries with extra unknown fields parse without error."""
        f = tmp_path / "extra_fields.jsonl"
        f.write_text(
            '{"type": "user", "sessionId": "s", "timestamp": "t", '
            '"extraField1": "value1", "extraField2": 42, "nested": {"a": 1}, '
            '"message": {"role": "user", "content": "content with extras"}}\n'
        )
        session = parse_session(f)
        assert session is not None
        assert len(session.turns) == 1
        assert session.turns[0].text == "content with extras"

    def test_only_meta_entries_returns_none(self, tmp_path):
        """A file containing only isMeta entries returns None."""
        f = tmp_path / "all_meta.jsonl"
        f.write_text(
            '{"type": "user", "sessionId": "s", "timestamp": "t", "isMeta": true, '
            '"message": {"role": "user", "content": "meta only"}}\n'
        )
        session = parse_session(f)
        assert session is None

    def test_only_unknown_type_returns_none(self, tmp_path):
        """A file containing only unknown-type entries returns None."""
        f = tmp_path / "all_summary.jsonl"
        f.write_text(
            '{"type": "summary", "sessionId": "s", "timestamp": "t", '
            '"message": {"role": "user", "content": "summary"}}\n'
        )
        session = parse_session(f)
        assert session is None


# ---------------------------------------------------------------------------
# _extract_text helper
# ---------------------------------------------------------------------------


class TestExtractText:
    """Unit tests for the _extract_text helper function."""

    def test_string_content(self):
        assert _extract_text("hello") == "hello"

    def test_empty_string(self):
        assert _extract_text("") == ""

    def test_text_block_list(self):
        content = [{"type": "text", "text": "hello"}]
        assert _extract_text(content) == "hello"

    def test_multiple_text_blocks(self):
        content = [
            {"type": "text", "text": "first"},
            {"type": "text", "text": "second"},
        ]
        assert _extract_text(content) == "first\nsecond"

    def test_mixed_blocks_only_text_extracted(self):
        content = [
            {"type": "text", "text": "visible"},
            {"type": "tool_use", "id": "t1", "name": "read", "input": {}},
            {"type": "thinking", "thinking": "hidden"},
        ]
        assert _extract_text(content) == "visible"

    def test_empty_list(self):
        assert _extract_text([]) == ""

    def test_none_content(self):
        assert _extract_text(None) == ""

    def test_integer_content(self):
        assert _extract_text(42) == ""

    def test_text_block_missing_text_key(self):
        content = [{"type": "text"}]
        assert _extract_text(content) == ""

    def test_non_dict_items_in_list(self):
        content = ["not a dict", {"type": "text", "text": "ok"}]
        assert _extract_text(content) == "ok"


# ---------------------------------------------------------------------------
# parse_session -- nonexistent file
# ---------------------------------------------------------------------------


class TestSchemaResilience:
    """Tests for resilience to unexpected message field types."""

    def test_null_message(self, tmp_path):
        """Entry with message: null is handled gracefully."""
        f = tmp_path / "null_msg.jsonl"
        f.write_text(
            '{"type": "user", "sessionId": "s", "timestamp": "t", "message": null}\n'
            '{"type": "user", "sessionId": "s", "timestamp": "t", '
            '"message": {"role": "user", "content": "real"}}\n'
        )
        session = parse_session(f)
        assert session is not None
        assert len(session.turns) == 1
        assert session.turns[0].text == "real"

    def test_string_message(self, tmp_path):
        """Entry with message as a string is handled gracefully."""
        f = tmp_path / "str_msg.jsonl"
        f.write_text(
            '{"type": "user", "sessionId": "s", "timestamp": "t", "message": "bad"}\n'
            '{"type": "user", "sessionId": "s", "timestamp": "t", '
            '"message": {"role": "user", "content": "real"}}\n'
        )
        session = parse_session(f)
        assert session is not None
        assert len(session.turns) == 1
        assert session.turns[0].text == "real"

    def test_integer_message(self, tmp_path):
        """Entry with message as an integer is handled gracefully."""
        f = tmp_path / "int_msg.jsonl"
        f.write_text(
            '{"type": "user", "sessionId": "s", "timestamp": "t", "message": 42}\n'
            '{"type": "user", "sessionId": "s", "timestamp": "t", '
            '"message": {"role": "user", "content": "real"}}\n'
        )
        session = parse_session(f)
        assert session is not None
        assert len(session.turns) == 1
        assert session.turns[0].text == "real"


class TestUserListContent:
    """Tests for extracting text from user list content."""

    def test_text_extracted_from_list(self, tmp_path):
        """User entries with list content containing text blocks are extracted."""
        f = tmp_path / "user_list.jsonl"
        f.write_text(
            '{"type": "user", "sessionId": "s", "timestamp": "t", '
            '"message": {"role": "user", "content": '
            '[{"type": "text", "text": "Hello from list"}]}}\n'
        )
        session = parse_session(f)
        assert session is not None
        assert len(session.turns) == 1
        assert session.turns[0].text == "Hello from list"
        assert session.turns[0].role == "user"

    def test_tool_result_only_list_skipped(self, tmp_path):
        """User entries with only tool_result blocks produce no turn."""
        f = tmp_path / "tool_only.jsonl"
        f.write_text(
            '{"type": "user", "sessionId": "s", "timestamp": "t", '
            '"message": {"role": "user", "content": '
            '[{"type": "tool_result", "tool_use_id": "t1", "content": "result"}]}}\n'
            '{"type": "user", "sessionId": "s", "timestamp": "t", '
            '"message": {"role": "user", "content": "fallback"}}\n'
        )
        session = parse_session(f)
        assert session is not None
        # Only the string-content entry produces a turn
        assert len(session.turns) == 1
        assert session.turns[0].text == "fallback"


class TestParseNonexistentFile:
    """parse_session handles missing files gracefully."""

    def test_returns_none(self):
        result = parse_session(Path("/nonexistent/file.jsonl"))
        assert result is None


class TestCommandFiltering:
    """Tests for filtering CLI commands and output (e.g., /exit, local-command-stdout)."""

    def test_exit_command_filtered(self, tmp_path):
        """User entries with /exit command are skipped."""
        f = tmp_path / "exit_cmd.jsonl"
        f.write_text(
            '{"type": "user", "sessionId": "s", "timestamp": "t1", '
            '"message": {"role": "user", "content": "How do I exit?"}}\n'
            '{"type": "assistant", "sessionId": "s", "timestamp": "t2", "requestId": "r1", '
            '"message": {"role": "assistant", "content": [{"type": "text", "text": "Press Ctrl+C"}]}}\n'
            '{"type": "user", "sessionId": "s", "timestamp": "t3", '
            '"message": {"role": "user", "content": "<command-name>/exit</command-name>\\n<command-message>exit</command-message>\\n<command-args></command-args>"}}\n'
            '{"type": "user", "sessionId": "s", "timestamp": "t4", '
            '"message": {"role": "user", "content": "<local-command-stdout>Bye!</local-command-stdout>"}}\n'
        )
        session = parse_session(f)
        assert session is not None
        # Should have 2 turns: user q + assistant response (exit command and stdout filtered)
        assert len(session.turns) == 2
        assert session.turns[0].role == "user"
        assert session.turns[0].text == "How do I exit?"
        assert session.turns[1].role == "assistant"
        assert session.turns[1].text == "Press Ctrl+C"

    def test_command_name_prefix_filtered(self, tmp_path):
        """User entries starting with <command- are filtered."""
        f = tmp_path / "cmd_filter.jsonl"
        f.write_text(
            '{"type": "user", "sessionId": "s", "timestamp": "t1", '
            '"message": {"role": "user", "content": "hello"}}\n'
            '{"type": "user", "sessionId": "s", "timestamp": "t2", '
            '"message": {"role": "user", "content": "<command-something>data</command-something>"}}\n'
        )
        session = parse_session(f)
        assert session is not None
        assert len(session.turns) == 1
        assert session.turns[0].text == "hello"

    def test_local_command_prefix_filtered(self, tmp_path):
        """User entries starting with <local-command- are filtered."""
        f = tmp_path / "local_cmd_filter.jsonl"
        f.write_text(
            '{"type": "user", "sessionId": "s", "timestamp": "t1", '
            '"message": {"role": "user", "content": "hello"}}\n'
            '{"type": "user", "sessionId": "s", "timestamp": "t2", '
            '"message": {"role": "user", "content": "<local-command-stdout>output</local-command-stdout>"}}\n'
        )
        session = parse_session(f)
        assert session is not None
        assert len(session.turns) == 1
        assert session.turns[0].text == "hello"


# ---------------------------------------------------------------------------
# New extended data model tests (TASK-019)
# ---------------------------------------------------------------------------


class TestParseThinkingBlocks:
    """Tests for thinking block extraction (TASK-002)."""

    @pytest.fixture()
    def session(self):
        return parse_session(FIXTURES / "tool_use_session.jsonl")

    def test_thinking_blocks_extracted(self, session):
        """Thinking blocks are extracted from tool_use_session.jsonl."""
        assert session is not None
        assistant_turns = [t for t in session.turns if t.role == "assistant"]
        # First assistant turn has a thinking block
        assert len(assistant_turns[0].thinking_blocks) >= 1

    def test_thinking_block_text(self, session):
        """Thinking block text is correctly extracted."""
        assert session is not None
        assistant_turns = [t for t in session.turns if t.role == "assistant"]
        thinking = assistant_turns[0].thinking_blocks[0]
        assert "I should read the file" in thinking.text


class TestTurnDefaults:
    """Tests for Turn default field values."""

    def test_thinking_blocks_defaults_to_empty_list(self):
        """thinking_blocks defaults to empty list."""
        turn = Turn(role="user", text="Test", timestamp="2026-02-07T10:00:00Z")
        assert turn.thinking_blocks == []

    def test_user_choice_defaults_to_none(self):
        """user_choice defaults to None."""
        turn = Turn(role="user", text="Test", timestamp="2026-02-07T10:00:00Z")
        assert turn.user_choice is None

    def test_sub_agent_refs_defaults_to_empty_list(self):
        """sub_agent_refs defaults to empty list."""
        turn = Turn(role="user", text="Test", timestamp="2026-02-07T10:00:00Z")
        assert turn.sub_agent_refs == []


class TestSubAgentRefDataclass:
    """Tests for SubAgentRef dataclass."""

    def test_create_with_all_fields(self):
        """SubAgentRef can be created with all fields."""
        from sessionbook.jsonl import SubAgentRef

        ref = SubAgentRef(
            agent_id="test-123",
            subagent_type="executor",
            description="Test task",
            summary="Task completed",
            duration_ms=5000,
            tool_use_count=3,
            transcript_path="./transcripts/test-123.html",
        )
        assert ref.agent_id == "test-123"
        assert ref.subagent_type == "executor"
        assert ref.description == "Test task"
        assert ref.summary == "Task completed"
        assert ref.duration_ms == 5000
        assert ref.tool_use_count == 3
        assert ref.transcript_path == "./transcripts/test-123.html"

    def test_create_with_optional_none(self):
        """SubAgentRef optional fields default to None."""
        from sessionbook.jsonl import SubAgentRef

        ref = SubAgentRef(
            agent_id="test-123",
            subagent_type="executor",
            description="Test task",
            summary="Task completed",
        )
        assert ref.duration_ms is None
        assert ref.tool_use_count is None
        assert ref.transcript_path is None


class TestUserChoiceDataclass:
    """Tests for UserChoice dataclass."""

    def test_create_user_choice(self):
        """UserChoice can be created with all fields."""
        from sessionbook.jsonl import UserChoice

        choice = UserChoice(
            question="What would you like?",
            options=["Option A", "Option B", "Option C"],
            selected_index=1,
        )
        assert choice.question == "What would you like?"
        assert choice.options == ["Option A", "Option B", "Option C"]
        assert choice.selected_index == 1


class TestSessionProgressEntries:
    """Tests for Session progress_entries field."""

    def test_session_has_progress_entries_field(self):
        """Session has progress_entries dict field."""
        session = Session(
            session_id="test",
            turns=[],
            filepath=Path("/tmp/test.jsonl"),
        )
        assert hasattr(session, "progress_entries")
        assert isinstance(session.progress_entries, dict)

    def test_progress_entries_defaults_to_empty_dict(self):
        """progress_entries defaults to empty dict."""
        session = Session(
            session_id="test",
            turns=[],
            filepath=Path("/tmp/test.jsonl"),
        )
        assert session.progress_entries == {}
