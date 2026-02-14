# Manual Test Plan -- sessionbook v1

> Execute each test manually against a real Claude Code installation.
> Record pass/fail and any notes in the Result column.

| ID     | Scenario | Steps | Expected Outcome | Result | Notes |
|--------|----------|-------|-------------------|--------|-------|
| MT-001 | Install in clean venv | `python -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]" && which sessionbook` | Path to `sessionbook` binary printed | | |
| MT-002 | Basic session capture | Run `sessionbook claude` in a project dir. Have a 2-3 turn conversation. Type `exit` or `/exit`. | `.sessionbook/` directory created with one `.ipynb` file | | |
| MT-003 | Notebook renders in VS Code | Open the `.ipynb` from MT-002 in VS Code. | Human prompts render as markdown cells. Model responses render as output text in code cells. No kernel warnings. | | |
| MT-004 | Notebook renders in Jupyter | Open the `.ipynb` from MT-002 in Jupyter (`jupyter notebook`). | Same rendering as MT-003. Markdown and output text display correctly. | | |
| MT-005 | `/clear` produces multiple notebooks | Run `sessionbook claude`. Chat briefly. Type `/clear`. Chat again. Exit. | Two `.ipynb` files in `.sessionbook/`, one per session. | | |
| MT-006 | Ctrl+C saves notebook | Run `sessionbook claude`. Chat briefly. Press Ctrl+C. | Session ends. Notebook is saved to `.sessionbook/`. | | |
| MT-007 | Sync retroactive conversion | Run `claude` directly (not through sessionbook). Have a conversation. Exit. Then run `sessionbook sync`. | Past session(s) appear as notebooks in `.sessionbook/`. | | |
| MT-008 | Interactive features pass-through | Run `sessionbook claude`. Test: Ctrl+G editor, `/help`, tab completion, slash commands. | All features work identically to running `claude` directly. Zero observable interference. | | |
| MT-009 | Verbose logging | Run `sessionbook --verbose claude`. Have a brief session. Exit. | Debug-level log messages appear on stderr with `[sessionbook]` prefix showing JSONL parsing details. | | |
| MT-010 | Existing `.sessionbook/` preserved | Create `.sessionbook/` with a dummy file. Run `sessionbook claude`. Chat. Exit. | Existing files untouched. New notebook added alongside them. | | |

## Prerequisites

- Claude Code CLI (`claude`) installed and on PATH
- Python 3.10+ with `pip install -e ".[dev]"` completed
- VS Code and/or Jupyter available for rendering tests

## Notes

- If Claude Code is not installed, MT-002 through MT-010 cannot be executed. Record as "SKIPPED - claude not available".
- MT-005 depends on Claude Code's `/clear` command creating a new session file in `~/.claude/projects/`.
- MT-006 tests signal handling. The parent process should catch SIGINT, forward it to the child, then convert sessions after the child exits.
