"""Integration tests for the sync subcommand (run_sync in capture.py).

Tests the retroactive session discovery and conversion pipeline
via run_sync, including multi-session handling, session filtering,
error paths, idempotency, and CLI dispatch.

Requirement trace: REQ-012, REQ-015, REQ-022, REQ-023, ERR-006, ERR-007.
"""

import json
from pathlib import Path
from unittest import mock

import pytest

from sessionbook.capture import run_sync
from sessionbook.jsonl import encode_project_path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_session_jsonl(
    directory: Path,
    filename: str = "session.jsonl",
    session_id: str = "sess-sync",
) -> Path:
    """Write a minimal 2-entry JSONL file (1 user, 1 assistant) to *directory*.

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
            "requestId": f"req-{session_id}",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": "Hi!"}],
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

    discover_sessions() in jsonl.py does a security check (SEC-006):
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
# TestRunSync -- integration suite for the sync subcommand
# ---------------------------------------------------------------------------


class TestRunSync:
    """Integration tests for run_sync (sync subcommand)."""

    def test_sync_all_sessions(self, tmp_path):
        """run_sync(None, ...) discovers all JSONL files and creates one
        notebook per session."""
        work_dir = tmp_path / "work"
        work_dir.mkdir()
        encoded = encode_project_path(work_dir)
        project_dir = tmp_path / "projects" / encoded
        project_dir.mkdir(parents=True)

        _write_session_jsonl(project_dir, "s1.jsonl", session_id="sess-a")
        _write_session_jsonl(project_dir, "s2.jsonl", session_id="sess-b")
        _write_session_jsonl(project_dir, "s3.jsonl", session_id="sess-c")

        with _patch_env(tmp_path, work_dir):
            rc = run_sync(None, True)

        assert rc == 0
        sessionbook_dir = work_dir / ".sessionbook"
        assert sessionbook_dir.is_dir(), ".sessionbook/ directory was not created"
        html_files = list(sessionbook_dir.glob("*.html"))
        assert len(html_files) == 3, f"Expected 3 HTML files, found {len(html_files)}"

    def test_sync_specific_session(self, tmp_path):
        """run_sync with a specific session_id converts only that session."""
        work_dir = tmp_path / "work"
        work_dir.mkdir()
        encoded = encode_project_path(work_dir)
        project_dir = tmp_path / "projects" / encoded
        project_dir.mkdir(parents=True)

        _write_session_jsonl(project_dir, "s1.jsonl", session_id="session-uuid-1")
        _write_session_jsonl(project_dir, "s2.jsonl", session_id="session-uuid-2")

        with _patch_env(tmp_path, work_dir):
            rc = run_sync("session-uuid-1", True)

        assert rc == 0
        sessionbook_dir = work_dir / ".sessionbook"
        assert sessionbook_dir.is_dir()
        html_files = list(sessionbook_dir.glob("*.html"))
        assert len(html_files) == 1, (
            f"Expected 1 HTML file for specific session, found {len(html_files)}"
        )

        # Verify the HTML file belongs to the correct session
        html_content = html_files[0].read_text()
        assert 'content="session-uuid-1"' in html_content

    def test_sync_no_project_dir(self, tmp_path):
        """run_sync returns 1 when the project directory does not exist."""
        work_dir = tmp_path / "work"
        work_dir.mkdir()
        # Do NOT create the project directory

        with _patch_env(tmp_path, work_dir):
            rc = run_sync(None, True)

        assert rc == 1
        assert not (work_dir / ".sessionbook").exists()

    def test_sync_empty_sessions(self, tmp_path):
        """Empty JSONL files produce no notebooks; run_sync returns 0."""
        work_dir = tmp_path / "work"
        work_dir.mkdir()
        encoded = encode_project_path(work_dir)
        project_dir = tmp_path / "projects" / encoded
        project_dir.mkdir(parents=True)

        # Write empty JSONL files (no extractable turns)
        (project_dir / "empty1.jsonl").write_text("")
        (project_dir / "empty2.jsonl").write_text("")

        with _patch_env(tmp_path, work_dir):
            rc = run_sync(None, True)

        assert rc == 0
        sessionbook_dir = work_dir / ".sessionbook"
        if sessionbook_dir.exists():
            html_files = list(sessionbook_dir.glob("*.html"))
            assert len(html_files) == 0, (
                f"Expected 0 HTML files for empty JSONL, found {len(html_files)}"
            )

    def test_sync_idempotent(self, tmp_path):
        """Running run_sync twice with the same data skips already-saved
        sessions.  The notebook count stays at 1 after the second run."""
        work_dir = tmp_path / "work"
        work_dir.mkdir()
        encoded = encode_project_path(work_dir)
        project_dir = tmp_path / "projects" / encoded
        project_dir.mkdir(parents=True)

        _write_session_jsonl(project_dir, "s1.jsonl", session_id="sess-idem")

        with _patch_env(tmp_path, work_dir):
            rc1 = run_sync(None, True)

        assert rc1 == 0
        html_files_after_first = list((work_dir / ".sessionbook").glob("*.html"))
        assert len(html_files_after_first) == 1

        with _patch_env(tmp_path, work_dir):
            rc2 = run_sync(None, True)

        assert rc2 == 0
        html_files_after_second = list((work_dir / ".sessionbook").glob("*.html"))
        # Second run skips already-saved session; count stays at 1
        assert len(html_files_after_second) == 1


# ---------------------------------------------------------------------------
# TestSyncCLIDispatch -- CLI entry point routing
# ---------------------------------------------------------------------------


class TestSyncCLIDispatch:
    """Verify the CLI main() dispatches sync subcommand to run_sync."""

    def test_sync_no_session_id(self):
        """'sessionbook sync' calls run_sync(None, ...)."""
        with (
            mock.patch("sessionbook.cli.run_sync", return_value=0) as mock_run_sync,
            mock.patch("sys.argv", ["sessionbook", "sync"]),
        ):
            with pytest.raises(SystemExit) as exc_info:
                from sessionbook.cli import main

                main()

            assert exc_info.value.code == 0
            mock_run_sync.assert_called_once()
            call_args = mock_run_sync.call_args
            assert call_args[0][0] is None  # session_id is None

    def test_sync_with_session_id(self):
        """'sessionbook sync my-session' calls run_sync('my-session', ...)."""
        with (
            mock.patch("sessionbook.cli.run_sync", return_value=0) as mock_run_sync,
            mock.patch("sys.argv", ["sessionbook", "sync", "my-session"]),
        ):
            with pytest.raises(SystemExit) as exc_info:
                from sessionbook.cli import main

                main()

            assert exc_info.value.code == 0
            mock_run_sync.assert_called_once()
            call_args = mock_run_sync.call_args
            assert call_args[0][0] == "my-session"  # session_id

    def test_sync_with_verbose(self):
        """'sessionbook --verbose sync' calls run_sync with verbose=True."""
        with (
            mock.patch("sessionbook.cli.run_sync", return_value=0) as mock_run_sync,
            mock.patch("sys.argv", ["sessionbook", "--verbose", "sync"]),
        ):
            with pytest.raises(SystemExit) as exc_info:
                from sessionbook.cli import main

                main()

            assert exc_info.value.code == 0
            mock_run_sync.assert_called_once()
            call_args = mock_run_sync.call_args
            assert call_args[0][1] is True  # verbose
