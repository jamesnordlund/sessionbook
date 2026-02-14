import errno
import logging
import os
import shutil
import signal
import sys
import time
from pathlib import Path

from sessionbook.jsonl import CLAUDE_DIR, encode_project_path, discover_sessions
from sessionbook.html import _existing_session_ids, save_html

log = logging.getLogger("sessionbook")

_child_pid: int = 0


def _forward_signal(signum: int, frame) -> None:
    """Forward signal to child process."""
    if _child_pid > 0:
        try:
            os.kill(_child_pid, signum)
        except ProcessLookupError:
            pass  # child already exited


def install_signal_handlers(child_pid: int) -> None:
    global _child_pid
    _child_pid = child_pid
    signal.signal(signal.SIGINT, _forward_signal)
    signal.signal(signal.SIGTERM, _forward_signal)


def convert_sessions(start_time: float, verbose: bool) -> None:
    """Convert JSONL sessions written since start_time to HTML."""
    cwd = Path.cwd()
    project_name = encode_project_path(cwd)
    project_dir = CLAUDE_DIR / project_name

    if not project_dir.is_dir():
        log.warning("Could not find project dir %s, skipping conversion", project_dir)
        return

    sessions = discover_sessions(project_dir, start_time)
    if not sessions:
        log.info("No session data found")
        return

    output_dir = cwd / ".sessionbook"
    seen = _existing_session_ids(output_dir)
    for session in sessions:
        if session.session_id in seen:
            log.info("Skipping already-saved session %s", session.session_id)
            continue
        if not session.turns:
            log.info("Skipping empty session %s", session.session_id)
            continue
        try:
            result = save_html(session, output_dir)
            if result:
                seen.add(session.session_id)
                log.info("Saved %s", result.name)
        except Exception:
            log.exception("Failed to save session %s", session.session_id)


def run_claude(args: list[str], verbose: bool) -> int:
    """Fork/exec claude, wait, convert sessions, return exit code."""
    claude_path = shutil.which("claude")
    if not claude_path:
        log.error("claude not found on PATH")
        return 1

    log.info("Wrapping claude in %s", os.getcwd())
    start_time = time.time()

    try:
        child_pid = os.fork()
    except OSError as e:
        log.error("fork failed: %s", e)
        return 1

    if child_pid == 0:
        # Child process
        try:
            os.execvp(claude_path, [claude_path] + args)
        except OSError as e:
            print(f"[sessionbook] exec failed: {e}", file=sys.stderr)
            os._exit(126)

    # Parent process
    install_signal_handlers(child_pid)

    try:
        while True:
            try:
                _, status = os.waitpid(child_pid, 0)
                break
            except OSError as e:
                if e.errno == errno.EINTR:
                    continue
                raise

        if os.WIFEXITED(status):
            exit_code = os.WEXITSTATUS(status)
        elif os.WIFSIGNALED(status):
            exit_code = 128 + os.WTERMSIG(status)
        else:
            exit_code = 1
    finally:
        # Reset signal handlers to avoid stale child_pid on subsequent calls
        global _child_pid
        _child_pid = 0
        signal.signal(signal.SIGINT, signal.SIG_DFL)
        signal.signal(signal.SIGTERM, signal.SIG_DFL)

    convert_sessions(start_time, verbose)

    return exit_code


def run_sync(session_id: str | None, verbose: bool) -> int:
    """Discover and convert existing sessions retroactively."""
    cwd = Path.cwd()
    project_name = encode_project_path(cwd)
    project_dir = CLAUDE_DIR / project_name

    if not project_dir.is_dir():
        log.warning("No project directory found at %s", project_dir)
        return 1

    sessions = discover_sessions(project_dir, start_time=0, session_id=session_id)
    output_dir = cwd / ".sessionbook"
    seen = _existing_session_ids(output_dir)
    count = 0

    for session in sessions:
        if session.session_id in seen:
            log.info("Skipping already-saved session %s", session.session_id)
            continue
        try:
            result = save_html(session, output_dir)
            if result is not None:
                seen.add(session.session_id)
                count += 1
        except Exception:
            log.exception("Failed to save session %s", session.session_id)

    log.info("Converted %d session(s)", count)
    return 0
