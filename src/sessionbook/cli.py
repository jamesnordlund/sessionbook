import argparse
import logging
import os
import sys

from sessionbook import __version__
from sessionbook.capture import run_claude, run_sync

log = logging.getLogger("sessionbook")


def configure_logging(verbose: bool) -> None:
    handler = logging.StreamHandler()  # defaults to stderr
    handler.setFormatter(logging.Formatter("[sessionbook] %(message)s"))
    log.addHandler(handler)
    log.setLevel(logging.DEBUG if verbose else logging.INFO)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="sessionbook",
        description="Save Claude Code sessions as self-contained HTML files",
    )
    parser.add_argument(
        "--version", action="version", version=f"sessionbook {__version__}"
    )
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")

    subparsers = parser.add_subparsers(dest="command")

    claude_parser = subparsers.add_parser(
        "claude", help="Wrap Claude Code and save session"
    )
    claude_parser.add_argument(
        "claude_args",
        nargs=argparse.REMAINDER,
        help="Arguments forwarded to claude",
    )

    sync_parser = subparsers.add_parser(
        "sync", help="Convert existing sessions to HTML"
    )
    sync_parser.add_argument(
        "session_id",
        nargs="?",
        default=None,
        help="Specific session ID to convert",
    )

    args = parser.parse_args()
    verbose = args.verbose or os.environ.get("sessionbook_DEBUG") == "1"
    configure_logging(verbose)

    if args.command is None:
        parser.print_help(sys.stderr)
        sys.exit(1)
    elif args.command == "claude":
        sys.exit(run_claude(args.claude_args, verbose))
    elif args.command == "sync":
        sys.exit(run_sync(args.session_id, verbose))
