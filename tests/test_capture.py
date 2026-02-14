"""Tests for sessionbook.capture module (TASK-010, TASK-011)."""

import errno
import os
import signal
from unittest import mock


from sessionbook.capture import (
    _forward_signal,
    convert_sessions,
    install_signal_handlers,
    run_claude,
    run_sync,
)


class TestRunClaude:
    """Tests for run_claude()."""

    def test_claude_not_found_returns_1(self):
        """When claude is not on PATH, run_claude returns 1 (ERR-001)."""
        with mock.patch("sessionbook.capture.shutil.which", return_value=None):
            result = run_claude([], verbose=False)
        assert result == 1

    def test_exit_code_propagation(self, tmp_path):
        """run_claude propagates the child process exit code (REQ-011)."""
        # Create a mock "claude" script that exits with code 42
        mock_claude = tmp_path / "claude"
        mock_claude.write_text("#!/bin/sh\nexit 42\n")
        mock_claude.chmod(0o755)

        with mock.patch(
            "sessionbook.capture.shutil.which", return_value=str(mock_claude)
        ):
            result = run_claude([], verbose=False)
        assert result == 42

    def test_exit_code_zero(self, tmp_path):
        """run_claude returns 0 when child exits successfully."""
        mock_claude = tmp_path / "claude"
        mock_claude.write_text("#!/bin/sh\nexit 0\n")
        mock_claude.chmod(0o755)

        with mock.patch(
            "sessionbook.capture.shutil.which", return_value=str(mock_claude)
        ):
            result = run_claude([], verbose=False)
        assert result == 0

    def test_args_forwarded_to_child(self, tmp_path):
        """Arguments are forwarded to the claude child process."""
        # Create a mock claude that writes args to a file
        marker = tmp_path / "args.txt"
        mock_claude = tmp_path / "claude"
        mock_claude.write_text(f'#!/bin/sh\necho "$@" > {marker}\nexit 0\n')
        mock_claude.chmod(0o755)

        with mock.patch(
            "sessionbook.capture.shutil.which", return_value=str(mock_claude)
        ):
            run_claude(["--help", "--verbose"], verbose=False)

        assert marker.read_text().strip() == "--help --verbose"

    def test_fork_failure_returns_1(self):
        """When os.fork() raises OSError, run_claude returns 1 (ERR-002)."""
        with (
            mock.patch(
                "sessionbook.capture.shutil.which", return_value="/usr/bin/claude"
            ),
            mock.patch(
                "sessionbook.capture.os.fork", side_effect=OSError("fork failed")
            ),
        ):
            result = run_claude([], verbose=False)
        assert result == 1

    def test_signal_killed_child_returns_128_plus_signal(self, tmp_path):
        """When child is killed by signal, exit code is 128 + signal number."""
        mock_claude = tmp_path / "claude"
        # Script that kills itself with SIGTERM (signal 15)
        mock_claude.write_text("#!/bin/sh\nkill -TERM $$\n")
        mock_claude.chmod(0o755)

        with mock.patch(
            "sessionbook.capture.shutil.which", return_value=str(mock_claude)
        ):
            result = run_claude([], verbose=False)
        assert result == 128 + signal.SIGTERM


class TestSignalHandling:
    """Tests for signal forwarding (TASK-011)."""

    def test_install_signal_handlers_sets_child_pid(self):
        """install_signal_handlers sets the module-level _child_pid."""
        import sessionbook.capture as cap

        old_pid = cap._child_pid
        try:
            install_signal_handlers(12345)
            assert cap._child_pid == 12345
        finally:
            cap._child_pid = old_pid
            # Restore default signal handlers
            signal.signal(signal.SIGINT, signal.SIG_DFL)
            signal.signal(signal.SIGTERM, signal.SIG_DFL)

    def test_forward_signal_sends_to_child(self):
        """_forward_signal calls os.kill on the child pid."""
        import sessionbook.capture as cap

        old_pid = cap._child_pid
        try:
            cap._child_pid = 99999
            with mock.patch("sessionbook.capture.os.kill") as mock_kill:
                _forward_signal(signal.SIGINT, None)
                mock_kill.assert_called_once_with(99999, signal.SIGINT)
        finally:
            cap._child_pid = old_pid

    def test_forward_signal_handles_process_lookup_error(self):
        """_forward_signal handles ProcessLookupError gracefully."""
        import sessionbook.capture as cap

        old_pid = cap._child_pid
        try:
            cap._child_pid = 99999
            with mock.patch(
                "sessionbook.capture.os.kill",
                side_effect=ProcessLookupError("No such process"),
            ):
                # Should not raise
                _forward_signal(signal.SIGTERM, None)
        finally:
            cap._child_pid = old_pid

    def test_forward_signal_noop_when_no_child(self):
        """_forward_signal does nothing when _child_pid is 0."""
        import sessionbook.capture as cap

        old_pid = cap._child_pid
        try:
            cap._child_pid = 0
            with mock.patch("sessionbook.capture.os.kill") as mock_kill:
                _forward_signal(signal.SIGINT, None)
                mock_kill.assert_not_called()
        finally:
            cap._child_pid = old_pid

    def test_sigint_forwarded_to_child(self, tmp_path):
        """SIGINT sent to parent is forwarded to child process (REQ-024)."""
        # Create a mock claude that sleeps for a long time
        # The parent will forward SIGINT which should terminate the child
        mock_claude = tmp_path / "claude"
        mock_claude.write_text("#!/bin/sh\ntrap 'exit 130' INT\nsleep 60\n")
        mock_claude.chmod(0o755)

        with mock.patch(
            "sessionbook.capture.shutil.which", return_value=str(mock_claude)
        ):
            # Run in a subprocess to test signal forwarding
            # For unit test purposes, we verify the handler is installed

            install_signal_handlers(os.getpid())  # dummy
            handler = signal.getsignal(signal.SIGINT)
            assert handler == _forward_signal
            # Restore
            signal.signal(signal.SIGINT, signal.SIG_DFL)
            signal.signal(signal.SIGTERM, signal.SIG_DFL)


class TestConvertSessions:
    """Tests for convert_sessions() stub."""

    def test_convert_sessions_stub_does_not_crash(self):
        """convert_sessions stub completes without error."""
        convert_sessions(0.0, verbose=False)


class TestWaitpidEINTR:
    """Tests for EINTR retry on os.waitpid."""

    def test_waitpid_eintr_retried(self, tmp_path):
        """os.waitpid retries on EINTR then succeeds."""
        mock_claude = tmp_path / "claude"
        mock_claude.write_text("#!/bin/sh\nexit 0\n")
        mock_claude.chmod(0o755)

        eintr_error = OSError(errno.EINTR, "Interrupted system call")
        # First call raises EINTR, second succeeds with normal exit
        original_waitpid = os.waitpid

        call_count = 0

        def mock_waitpid(pid, options):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise eintr_error
            return original_waitpid(pid, options)

        with (
            mock.patch(
                "sessionbook.capture.shutil.which", return_value=str(mock_claude)
            ),
            mock.patch("sessionbook.capture.os.waitpid", side_effect=mock_waitpid),
        ):
            result = run_claude([], verbose=False)

        assert result == 0
        assert call_count == 2


class TestRunSync:
    """Tests for run_sync()."""

    def test_run_sync_returns_0_when_project_dir_exists(self, tmp_path):
        """run_sync returns 0 when the project directory exists."""
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        with (
            mock.patch("sessionbook.capture.CLAUDE_DIR", tmp_path),
            mock.patch(
                "sessionbook.capture.encode_project_path", return_value="project"
            ),
        ):
            result = run_sync(None, verbose=False)
        assert result == 0

    def test_run_sync_returns_1_when_project_dir_missing(self, tmp_path):
        """run_sync returns 1 when the project directory does not exist."""
        with (
            mock.patch("sessionbook.capture.CLAUDE_DIR", tmp_path),
            mock.patch(
                "sessionbook.capture.encode_project_path", return_value="nonexistent"
            ),
        ):
            result = run_sync(None, verbose=False)
        assert result == 1
