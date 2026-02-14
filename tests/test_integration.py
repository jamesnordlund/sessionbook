"""Integration tests for the sessionbook claude pipeline (TASK-013, TASK-020).

Tests the convert_sessions pipeline end-to-end using mock JSONL data
and patched module-level constants. Does NOT fork processes -- instead
tests the core orchestration logic (convert_sessions) and verifies
that JSONL files are correctly discovered, parsed, and converted into
valid HTML files.

Requirement trace: REQ-002, REQ-011, REQ-012, REQ-013, REQ-015,
REQ-021, REQ-022, REQ-023, REQ-025, ERR-001, ERR-006, ERR-007, DI-008.
"""

import json
import os
import time
from pathlib import Path
from unittest import mock


from sessionbook.capture import convert_sessions
from sessionbook.jsonl import encode_project_path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FIXTURES = Path(__file__).parent / "fixtures"


def _write_session_jsonl(
    directory: Path,
    filename: str = "session.jsonl",
    session_id: str = "sess-int",
) -> Path:
    """Write a valid 4-entry JSONL file (2 user, 2 assistant) to *directory*.

    Returns the path to the created file.
    """
    entries = [
        {
            "type": "user",
            "sessionId": session_id,
            "timestamp": "2026-02-07T10:00:00Z",
            "message": {"role": "user", "content": "Hello"},
        },
        {
            "type": "assistant",
            "sessionId": session_id,
            "timestamp": "2026-02-07T10:00:01Z",
            "requestId": "req-1",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": "Hi there!"}],
            },
        },
        {
            "type": "user",
            "sessionId": session_id,
            "timestamp": "2026-02-07T10:00:02Z",
            "message": {"role": "user", "content": "Bye"},
        },
        {
            "type": "assistant",
            "sessionId": session_id,
            "timestamp": "2026-02-07T10:00:03Z",
            "requestId": "req-2",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": "Goodbye!"}],
            },
        },
    ]
    filepath = directory / filename
    with open(filepath, "w") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")
    return filepath


def _patch_env(tmp_path: Path, work_dir: Path):
    """Return a combined context-manager that patches CLAUDE_DIR in both
    modules and makes Path.cwd() return *work_dir*.

    capture.py imports CLAUDE_DIR at module level via:
        from sessionbook.jsonl import CLAUDE_DIR
    so the binding in the capture namespace must be patched separately.

    discover_sessions() in jsonl.py does a security check:
        project_dir.resolve().relative_to(CLAUDE_DIR.resolve())
    so jsonl.CLAUDE_DIR must also point to the same temp root.
    """
    projects_dir = tmp_path / "projects"

    class _Ctx:
        """Stacked context-manager for the three patches."""

        def __enter__(self):
            self._p1 = mock.patch("sessionbook.capture.CLAUDE_DIR", projects_dir)
            self._p2 = mock.patch("sessionbook.jsonl.CLAUDE_DIR", projects_dir)
            self._p3 = mock.patch.object(Path, "cwd", return_value=work_dir)
            self._p1.__enter__()
            self._p2.__enter__()
            self._p3.__enter__()
            return self

        def __exit__(self, *exc):
            self._p3.__exit__(*exc)
            self._p2.__exit__(*exc)
            self._p1.__exit__(*exc)

    return _Ctx()


# ---------------------------------------------------------------------------
# TestConvertSessionsPipeline -- main integration suite
# ---------------------------------------------------------------------------


class TestConvertSessionsPipeline:
    """Integration tests for convert_sessions (TASK-012, TASK-013)."""

    # -- full pipeline -------------------------------------------------

    def test_full_pipeline_creates_html(self, tmp_path):
        """convert_sessions discovers a JSONL session and writes a valid
        HTML file into .sessionbook/ (REQ-012, REQ-015, REQ-021, REQ-027)."""
        work_dir = tmp_path / "work"
        work_dir.mkdir()
        encoded = encode_project_path(work_dir)
        project_dir = tmp_path / "projects" / encoded
        project_dir.mkdir(parents=True)
        _write_session_jsonl(project_dir)

        with _patch_env(tmp_path, work_dir):
            convert_sessions(start_time=0, verbose=True)

        sessionbook_dir = work_dir / ".sessionbook"
        assert sessionbook_dir.is_dir(), ".sessionbook/ directory was not created"

        html_files = list(sessionbook_dir.glob("*.html"))
        assert len(html_files) == 1, f"Expected 1 HTML file, found {len(html_files)}"

        # Validate the HTML content
        html_content = html_files[0].read_text()
        assert "<!DOCTYPE html>" in html_content
        assert 'name="sessionbook-session-id"' in html_content
        assert "sess-int" in html_content

    def test_full_pipeline_html_content(self, tmp_path):
        """HTML file contains the expected user prompts and assistant
        responses (REQ-017, REQ-028, REQ-029)."""
        work_dir = tmp_path / "work"
        work_dir.mkdir()
        encoded = encode_project_path(work_dir)
        project_dir = tmp_path / "projects" / encoded
        project_dir.mkdir(parents=True)
        _write_session_jsonl(project_dir)

        with _patch_env(tmp_path, work_dir):
            convert_sessions(start_time=0, verbose=True)

        html_files = list((work_dir / ".sessionbook").glob("*.html"))
        html_content = html_files[0].read_text()

        # Check for user and assistant content
        assert "Hello" in html_content
        assert "Hi there!" in html_content
        assert "Bye" in html_content
        assert "Goodbye!" in html_content

        # Check for turn structure
        assert 'class="turn turn-user"' in html_content
        assert 'class="turn turn-assistant"' in html_content

    def test_full_pipeline_metadata(self, tmp_path):
        """Generated HTML has sessionbook metadata (REQ-032, REQ-033)."""
        work_dir = tmp_path / "work"
        work_dir.mkdir()
        encoded = encode_project_path(work_dir)
        project_dir = tmp_path / "projects" / encoded
        project_dir.mkdir(parents=True)
        _write_session_jsonl(project_dir)

        with _patch_env(tmp_path, work_dir):
            convert_sessions(start_time=0, verbose=True)

        html_files = list((work_dir / ".sessionbook").glob("*.html"))
        html_content = html_files[0].read_text()

        assert 'name="sessionbook-session-id" content="sess-int"' in html_content
        assert 'name="sessionbook-converted"' in html_content

    def test_full_pipeline_file_permissions(self, tmp_path):
        """Generated HTML has 0o644 permissions (SEC-004)."""
        work_dir = tmp_path / "work"
        work_dir.mkdir()
        encoded = encode_project_path(work_dir)
        project_dir = tmp_path / "projects" / encoded
        project_dir.mkdir(parents=True)
        _write_session_jsonl(project_dir)

        with _patch_env(tmp_path, work_dir):
            convert_sessions(start_time=0, verbose=True)

        html_files = list((work_dir / ".sessionbook").glob("*.html"))
        mode = os.stat(html_files[0]).st_mode & 0o777
        assert mode == 0o644, f"Expected 0o644, got {oct(mode)}"

    def test_full_pipeline_no_temp_files(self, tmp_path):
        """No .tmp files remain after HTML is saved (DI-009)."""
        work_dir = tmp_path / "work"
        work_dir.mkdir()
        encoded = encode_project_path(work_dir)
        project_dir = tmp_path / "projects" / encoded
        project_dir.mkdir(parents=True)
        _write_session_jsonl(project_dir)

        with _patch_env(tmp_path, work_dir):
            convert_sessions(start_time=0, verbose=True)

        sessionbook_dir = work_dir / ".sessionbook"
        tmp_files = list(sessionbook_dir.glob("*.tmp"))
        assert len(tmp_files) == 0, f"Found leftover tmp files: {tmp_files}"

    def test_no_ipynb_files_created(self, tmp_path):
        """No .ipynb files are created (REQ-015)."""
        work_dir = tmp_path / "work"
        work_dir.mkdir()
        encoded = encode_project_path(work_dir)
        project_dir = tmp_path / "projects" / encoded
        project_dir.mkdir(parents=True)
        _write_session_jsonl(project_dir)

        with _patch_env(tmp_path, work_dir):
            convert_sessions(start_time=0, verbose=True)

        sessionbook_dir = work_dir / ".sessionbook"
        ipynb_files = list(sessionbook_dir.glob("*.ipynb"))
        assert len(ipynb_files) == 0, f"Found unexpected .ipynb files: {ipynb_files}"

    # -- no project directory ------------------------------------------

    def test_no_project_dir_does_not_crash(self, tmp_path):
        """convert_sessions with a nonexistent project directory does not
        crash and does not create .sessionbook/ (ERR-007)."""
        work_dir = tmp_path / "work"
        work_dir.mkdir()
        # Do NOT create the project directory

        with _patch_env(tmp_path, work_dir):
            # Should log a warning and return without error
            convert_sessions(start_time=0, verbose=True)

        assert not (work_dir / ".sessionbook").exists()

    # -- mtime filtering -----------------------------------------------

    def test_mtime_filtering_excludes_old_sessions(self, tmp_path):
        """convert_sessions with a non-zero start_time skips JSONL files
        with older modification times (REQ-022)."""
        work_dir = tmp_path / "work"
        work_dir.mkdir()
        encoded = encode_project_path(work_dir)
        project_dir = tmp_path / "projects" / encoded
        project_dir.mkdir(parents=True)

        # Write an "old" session file
        _write_session_jsonl(project_dir, "old.jsonl", session_id="sess-old")
        old_file = project_dir / "old.jsonl"
        old_time = time.time() - 200
        os.utime(old_file, (old_time, old_time))

        # Record a start_time after the old file
        start = time.time() - 50

        # Write a "new" session file (current mtime)
        _write_session_jsonl(project_dir, "new.jsonl", session_id="sess-new")

        with _patch_env(tmp_path, work_dir):
            convert_sessions(start_time=start, verbose=True)

        sessionbook_dir = work_dir / ".sessionbook"
        assert sessionbook_dir.is_dir()
        html_files = list(sessionbook_dir.glob("*.html"))
        assert len(html_files) == 1, (
            f"Expected 1 HTML file (new only), found {len(html_files)}"
        )

    def test_mtime_filtering_start_time_zero_includes_all(self, tmp_path):
        """start_time=0 means no filtering; all sessions are converted."""
        work_dir = tmp_path / "work"
        work_dir.mkdir()
        encoded = encode_project_path(work_dir)
        project_dir = tmp_path / "projects" / encoded
        project_dir.mkdir(parents=True)

        _write_session_jsonl(project_dir, "s1.jsonl", session_id="sess-1")
        # Set to an old mtime
        old_time = time.time() - 86400
        os.utime(project_dir / "s1.jsonl", (old_time, old_time))

        _write_session_jsonl(project_dir, "s2.jsonl", session_id="sess-2")

        with _patch_env(tmp_path, work_dir):
            convert_sessions(start_time=0, verbose=True)

        html_files = list((work_dir / ".sessionbook").glob("*.html"))
        assert len(html_files) == 2

    # -- multiple sessions (simulating /clear) -------------------------

    def test_multiple_sessions_produce_multiple_notebooks(self, tmp_path):
        """Multiple JSONL files in the project directory produce one
        notebook each, simulating /clear behavior (REQ-022, REQ-023)."""
        work_dir = tmp_path / "work"
        work_dir.mkdir()
        encoded = encode_project_path(work_dir)
        project_dir = tmp_path / "projects" / encoded
        project_dir.mkdir(parents=True)

        _write_session_jsonl(project_dir, "session1.jsonl", session_id="sess-a")
        _write_session_jsonl(project_dir, "session2.jsonl", session_id="sess-b")
        _write_session_jsonl(project_dir, "session3.jsonl", session_id="sess-c")

        with _patch_env(tmp_path, work_dir):
            convert_sessions(start_time=0, verbose=True)

        html_files = list((work_dir / ".sessionbook").glob("*.html"))
        assert len(html_files) == 3, f"Expected 3 HTML files, found {len(html_files)}"

    def test_multiple_sessions_each_valid(self, tmp_path):
        """Each notebook produced by multiple sessions is individually
        nbformat-valid (REQ-027, REQ-034)."""
        work_dir = tmp_path / "work"
        work_dir.mkdir()
        encoded = encode_project_path(work_dir)
        project_dir = tmp_path / "projects" / encoded
        project_dir.mkdir(parents=True)

        _write_session_jsonl(project_dir, "session1.jsonl", session_id="sess-x")
        _write_session_jsonl(project_dir, "session2.jsonl", session_id="sess-y")

        with _patch_env(tmp_path, work_dir):
            convert_sessions(start_time=0, verbose=True)

        for html_path in (work_dir / ".sessionbook").glob("*.html"):
            html_content = html_path.read_text()
            assert "<!DOCTYPE html>" in html_content
            assert 'name="sessionbook-session-id"' in html_content

    # -- empty session -------------------------------------------------

    def test_empty_session_produces_no_notebook(self, tmp_path):
        """An empty JSONL file produces no notebook (ERR-006)."""
        work_dir = tmp_path / "work"
        work_dir.mkdir()
        encoded = encode_project_path(work_dir)
        project_dir = tmp_path / "projects" / encoded
        project_dir.mkdir(parents=True)
        (project_dir / "empty.jsonl").write_text("")

        with _patch_env(tmp_path, work_dir):
            convert_sessions(start_time=0, verbose=True)

        sessionbook_dir = work_dir / ".sessionbook"
        if sessionbook_dir.exists():
            html_files = list(sessionbook_dir.glob("*.html"))
            assert len(html_files) == 0, (
                f"Expected 0 HTML files for empty JSONL, found {len(html_files)}"
            )

    def test_only_meta_entries_produces_no_notebook(self, tmp_path):
        """A JSONL file containing only isMeta entries produces no
        notebook (DI-002, ERR-006)."""
        work_dir = tmp_path / "work"
        work_dir.mkdir()
        encoded = encode_project_path(work_dir)
        project_dir = tmp_path / "projects" / encoded
        project_dir.mkdir(parents=True)
        meta_entry = json.dumps(
            {
                "type": "user",
                "sessionId": "sess-meta",
                "timestamp": "2026-02-07T10:00:00Z",
                "isMeta": True,
                "message": {"role": "user", "content": "System context only"},
            }
        )
        (project_dir / "meta_only.jsonl").write_text(meta_entry + "\n")

        with _patch_env(tmp_path, work_dir):
            convert_sessions(start_time=0, verbose=True)

        sessionbook_dir = work_dir / ".sessionbook"
        if sessionbook_dir.exists():
            html_files = list(sessionbook_dir.glob("*.html"))
            assert len(html_files) == 0

    # -- existing .sessionbook/ directory reuse -------------------------

    def test_existing_sessionbook_dir_is_reused(self, tmp_path):
        """When .sessionbook/ already exists, convert_sessions adds a new
        HTML file without removing existing files (REQ-013, NEG-005)."""
        work_dir = tmp_path / "work"
        work_dir.mkdir()
        encoded = encode_project_path(work_dir)
        project_dir = tmp_path / "projects" / encoded
        project_dir.mkdir(parents=True)

        # Pre-create .sessionbook/ with a dummy file
        sessionbook_dir = work_dir / ".sessionbook"
        sessionbook_dir.mkdir()
        existing_file = sessionbook_dir / "existing_file.html"
        existing_file.write_text("<!DOCTYPE html><html></html>")

        _write_session_jsonl(project_dir)

        with _patch_env(tmp_path, work_dir):
            convert_sessions(start_time=0, verbose=True)

        # The existing file should still be there
        assert existing_file.exists(), "Existing HTML file was deleted"
        # Plus the new one
        all_html_files = list(sessionbook_dir.glob("*.html"))
        assert len(all_html_files) == 2

    # -- collision handling --------------------------------------------

    def test_filename_collision_produces_suffix(self, tmp_path):
        """When two sessions produce the same timestamp-based filename,
        the second gets a numeric suffix (REQ-038)."""
        work_dir = tmp_path / "work"
        work_dir.mkdir()
        encoded = encode_project_path(work_dir)
        project_dir = tmp_path / "projects" / encoded
        project_dir.mkdir(parents=True)

        # Both sessions have identical timestamps, so they will generate
        # the same filename
        _write_session_jsonl(project_dir, "session1.jsonl", session_id="sess-dup-1")
        _write_session_jsonl(project_dir, "session2.jsonl", session_id="sess-dup-2")

        with _patch_env(tmp_path, work_dir):
            convert_sessions(start_time=0, verbose=True)

        html_files = sorted(
            (work_dir / ".sessionbook").glob("*.html"),
            key=lambda p: p.name,
        )
        assert len(html_files) == 2
        # One should have a -1 suffix at the end of its stem
        names = [f.stem for f in html_files]
        suffixed = [n for n in names if n.endswith("-1")]
        assert len(suffixed) == 1, (
            f"Expected one filename ending with -1 suffix; got names: {names}"
        )

    # -- idempotency: independent runs (DI-008) -----------------------

    def test_independent_runs_produce_independent_html_files(self, tmp_path):
        """Two separate convert_sessions calls produce independent HTML
        files (DI-008)."""
        work_dir = tmp_path / "work"
        work_dir.mkdir()
        encoded = encode_project_path(work_dir)
        project_dir = tmp_path / "projects" / encoded
        project_dir.mkdir(parents=True)

        # First run
        _write_session_jsonl(project_dir, "first.jsonl", session_id="sess-first")

        with _patch_env(tmp_path, work_dir):
            convert_sessions(start_time=0, verbose=True)

        first_run_html_files = set(
            f.name for f in (work_dir / ".sessionbook").glob("*.html")
        )
        assert len(first_run_html_files) == 1

        # Second run with a different session
        _write_session_jsonl(project_dir, "second.jsonl", session_id="sess-second")

        with _patch_env(tmp_path, work_dir):
            convert_sessions(start_time=0, verbose=True)

        all_html_files = set(f.name for f in (work_dir / ".sessionbook").glob("*.html"))
        # Both the old and new HTML file should exist
        assert len(all_html_files) >= 2
        assert first_run_html_files.issubset(all_html_files)

    # -- malformed JSONL resilience ------------------------------------

    def test_malformed_jsonl_does_not_crash(self, tmp_path):
        """A JSONL file with a mix of valid and malformed lines does not
        crash convert_sessions; valid turns produce a notebook (ERR-004)."""
        work_dir = tmp_path / "work"
        work_dir.mkdir()
        encoded = encode_project_path(work_dir)
        project_dir = tmp_path / "projects" / encoded
        project_dir.mkdir(parents=True)

        content = (
            '{"type": "user", "sessionId": "sess-bad", "timestamp": "2026-02-07T10:00:00Z", '
            '"message": {"role": "user", "content": "Good line"}}\n'
            "THIS IS NOT JSON\n"
            '{"type": "assistant", "sessionId": "sess-bad", "timestamp": "2026-02-07T10:00:01Z", '
            '"requestId": "req-b1", '
            '"message": {"role": "assistant", "content": [{"type": "text", "text": "Valid response"}]}}\n'
        )
        (project_dir / "mixed.jsonl").write_text(content)

        with _patch_env(tmp_path, work_dir):
            convert_sessions(start_time=0, verbose=True)

        html_files = list((work_dir / ".sessionbook").glob("*.html"))
        assert len(html_files) == 1

        html_content = html_files[0].read_text()
        assert "Good line" in html_content
        assert "Valid response" in html_content

    # -- unicode content round-trip ------------------------------------

    def test_unicode_content_preserved(self, tmp_path):
        """Unicode content (CJK, emoji, accented chars) survives the full
        pipeline: JSONL -> parse -> notebook -> disk -> read (REQ-020)."""
        work_dir = tmp_path / "work"
        work_dir.mkdir()
        encoded = encode_project_path(work_dir)
        project_dir = tmp_path / "projects" / encoded
        project_dir.mkdir(parents=True)

        entries = [
            {
                "type": "user",
                "sessionId": "sess-uni",
                "timestamp": "2026-02-07T10:00:00Z",
                "message": {
                    "role": "user",
                    "content": "\u4f60\u597d\u4e16\u754c \U0001f389",
                },
            },
            {
                "type": "assistant",
                "sessionId": "sess-uni",
                "timestamp": "2026-02-07T10:00:01Z",
                "requestId": "req-u1",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "caf\u00e9 r\u00e9sum\u00e9"}],
                },
            },
        ]
        filepath = project_dir / "unicode.jsonl"
        with open(filepath, "w", encoding="utf-8") as f:
            for entry in entries:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

        with _patch_env(tmp_path, work_dir):
            convert_sessions(start_time=0, verbose=True)

        html_files = list((work_dir / ".sessionbook").glob("*.html"))
        assert len(html_files) == 1
        html_content = html_files[0].read_text()

        # Check unicode content is preserved
        assert (
            "\u4f60\u597d\u4e16\u754c" in html_content
        )  # "你好世界" (Hello World in Chinese)
        assert "\U0001f389" in html_content  # 🎉 emoji
        assert "caf\u00e9" in html_content  # café
        assert "r\u00e9sum\u00e9" in html_content  # résumé

    # -- HTML structure invariants ---------------------------------

    def test_html_turn_ordering(self, tmp_path):
        """Turns appear in conversation order with correct classes (REQ-030)."""
        work_dir = tmp_path / "work"
        work_dir.mkdir()
        encoded = encode_project_path(work_dir)
        project_dir = tmp_path / "projects" / encoded
        project_dir.mkdir(parents=True)
        _write_session_jsonl(project_dir)

        with _patch_env(tmp_path, work_dir):
            convert_sessions(start_time=0, verbose=True)

        html_files = list((work_dir / ".sessionbook").glob("*.html"))
        html_content = html_files[0].read_text()

        # Check for turn structure with correct ordering
        hello_idx = html_content.find("Hello")
        hi_there_idx = html_content.find("Hi there!")
        bye_idx = html_content.find("Bye")
        goodbye_idx = html_content.find("Goodbye!")

        assert hello_idx < hi_there_idx < bye_idx < goodbye_idx
        assert 'class="turn turn-user"' in html_content
        assert 'class="turn turn-assistant"' in html_content


# ---------------------------------------------------------------------------
# TestMockClaudeScripts -- verify fixture scripts exist and are well-formed
# ---------------------------------------------------------------------------


class TestMockClaudeScripts:
    """Verify the mock shell scripts in tests/fixtures/ are valid."""

    def test_mock_claude_sh_exists(self):
        path = FIXTURES / "mock_claude.sh"
        assert path.exists(), f"Missing fixture: {path}"

    def test_mock_claude_sh_contains_jsonl(self):
        content = (FIXTURES / "mock_claude.sh").read_text()
        assert "sess-mock" in content
        assert "req-m1" in content
        assert "exit 0" in content

    def test_mock_claude_exit42_sh_exists(self):
        path = FIXTURES / "mock_claude_exit42.sh"
        assert path.exists(), f"Missing fixture: {path}"

    def test_mock_claude_exit42_sh_contains_jsonl(self):
        content = (FIXTURES / "mock_claude_exit42.sh").read_text()
        assert "sess-exit42" in content
        assert "exit 42" in content
