# sessionbook

Save Claude Code sessions as self-contained HTML files.

sessionbook wraps the `claude` CLI and, on exit, converts the session's JSONL
log into a `.html` file in the local `.sessionbook/` directory. The output is a
chat-style transcript with collapsible thinking blocks, user-choice decision
cards, and linked sub-agent transcripts. Each file is self-contained (inline
CSS, no external dependencies) and opens in any browser.

## Requirements

- Python 3.10+
- [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) installed and on `$PATH`
- macOS (uses `os.fork`)

## Installation

```sh
pip install sessionbook
```

For development (includes pytest):

```sh
pip install -e ".[dev]"
```

## Quick Start

### Capture a session

```sh
sessionbook claude
```

This launches Claude Code exactly as if you ran `claude` directly. All
interactive features work unchanged (Ctrl+G, slash commands, MCP tools). When
the session ends, sessionbook reads the JSONL session file and saves an HTML file
to `.sessionbook/<TIMESTAMP>.html`.

If you use `/clear` during a session, each sub-session is saved as a separate
file.

### Arguments are forwarded

Any arguments after `claude` are passed through to the Claude Code CLI:

```sh
sessionbook claude --model sonnet
sessionbook claude -p "Explain this repo"
```

### Convert existing sessions

Retroactively convert past Claude Code sessions for the current project
directory:

```sh
sessionbook sync
```

Or convert a specific session by ID:

```sh
sessionbook sync <session-id>
```

## Output Format

HTML files are written to `.sessionbook/` in the working directory. Each file is
named with a local-time timestamp: `2026-02-07T14-32-01.html`.

```
.sessionbook/
  2026-02-10T21-43-08.html
  2026-02-10T21-43-08/          # sub-agent transcripts (if any)
    agent-aa5abe3.html
    agent-bc7f012.html
```

### Session layout

Each turn in the conversation is rendered as a visually distinct card:

- **User turns** — light blue background with the user's prompt text
- **Assistant turns** — light gray background with the model's response
- **Thinking blocks** — collapsed `<details>` elements (click to expand)
- **Decision cards** — when the model presented options via AskUserQuestion,
  the card shows the question, all options, and which one was selected
- **Sub-agent cards** — when the model forked work to a sub-agent (e.g.,
  Explore, executor), the card shows a summary and links to a separate HTML
  file with the full sub-agent transcript

### What is captured

| Content | Included |
|---------|----------|
| User prompts | Yes |
| Model responses (text) | Yes |
| Thinking blocks | Yes (collapsed) |
| User choice interactions | Yes (decision cards) |
| Sub-agent transcripts | Yes (linked out) |
| Tool use / tool results | No (filtered out) |
| System context (isMeta) | No (filtered out) |

## CLI Reference

```
sessionbook <subcommand> [options] [args...]

Subcommands:
  claude    Wrap Claude Code and save session as HTML on exit
  sync      Convert existing Claude Code sessions to HTML

Options:
  --verbose    Enable debug-level logging to stderr
  --version    Print version and exit
  --help       Print usage and exit

Environment variables:
  sessionbook_DEBUG=1    Equivalent to --verbose
```

Exit codes mirror the `claude` child process. If `claude` exits 0, `sessionbook`
exits 0.

## How It Works

1. `sessionbook claude` calls `os.fork()` + `os.execvp("claude", ...)`. The
   child process inherits the terminal directly, so Claude Code behaves
   identically to a direct invocation. The parent process is blocked in
   `os.waitpid()` and never touches stdin/stdout.
2. After the child exits, the parent reads JSONL session files from
   `~/.claude/projects/` that were modified during the session.
3. Each session's user and assistant turns are extracted (with `requestId`
   collapsing for streamed responses), along with thinking blocks, user
   choices, and sub-agent references.
4. The session is rendered as self-contained HTML with inline CSS and written
   atomically (tempfile + rename) to `.sessionbook/`.

Zero runtime dependencies. The HTML is constructed from Python f-strings with
`html.escape()` for all user content.

## Uninstall

```sh
pip uninstall sessionbook
```

The `.sessionbook/` directories contain only generated HTML files and can be
deleted at your discretion.

## License

MIT
