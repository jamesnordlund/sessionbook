import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from sessionbook.util import validate_agent_id

log = logging.getLogger("sessionbook")

CLAUDE_DIR = Path.home() / ".claude" / "projects"


@dataclass
class ThinkingBlock:
    """A thinking block from an assistant message content array.

    Extracted from content blocks where type="thinking".
    """

    text: str


@dataclass
class UserChoice:
    """A user choice interaction from AskUserQuestion tool.

    Extracted from tool_use block where name="AskUserQuestion"
    and corresponding tool_result block.
    """

    question: str
    options: list[str]
    selected_index: int


@dataclass
class SubAgentRef:
    """A reference to a sub-agent transcript spawned via Task tool.

    Extracted from tool_use block where name="Task" and corresponding tool_result.
    """

    agent_id: str
    subagent_type: str
    description: str
    summary: str
    duration_ms: int | None = None
    tool_use_count: int | None = None
    transcript_path: str | None = None


@dataclass
class Turn:
    """A single user message or assistant response in the conversation.

    Extended to include thinking blocks, user choices, and sub-agent references.
    """

    role: str
    text: str
    timestamp: str
    thinking_blocks: list[ThinkingBlock] = field(default_factory=list)
    user_choice: UserChoice | None = None
    sub_agent_refs: list[SubAgentRef] = field(default_factory=list)


@dataclass
class Session:
    session_id: str
    turns: list[Turn]
    filepath: Path
    progress_entries: dict[str, list[dict]] = field(default_factory=dict)


def encode_project_path(cwd: Path) -> str:
    """Convert absolute path to Claude Code's project directory name.

    /Users/james/foo -> -Users-james-foo
    """
    return str(cwd).replace("/", "-")


def _extract_text(content) -> str:
    """Extract text from message content (string or content block array)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "\n".join(parts) if parts else ""
    return ""


def parse_session(filepath: Path) -> Session | None:
    """Parse a single JSONL file into a Session."""
    entries = []
    session_id = None
    progress_entries_by_parent: dict[str, list[dict]] = {}

    try:
        with open(filepath) as f:
            for lineno, raw_line in enumerate(f, 1):
                raw_line = raw_line.strip()
                if not raw_line:
                    continue
                try:
                    entry = json.loads(raw_line)
                except json.JSONDecodeError:
                    log.warning(
                        "Skipping malformed line %d in %s", lineno, filepath.name
                    )
                    continue

                entry_type = entry.get("type")

                # Collect progress entries for sub-agent transcript reconstruction (TASK-004)
                if entry_type == "progress":
                    data = entry.get("data", {})
                    if data.get("type") == "agent_progress":
                        parent_tool_use_id = entry.get("parentToolUseID", "")
                        if parent_tool_use_id:
                            if parent_tool_use_id not in progress_entries_by_parent:
                                progress_entries_by_parent[parent_tool_use_id] = []
                            progress_entries_by_parent[parent_tool_use_id].append(entry)
                    continue

                if entry_type not in ("user", "assistant"):
                    continue
                if entry.get("isMeta"):
                    continue
                if entry.get("isSidechain"):
                    continue

                if session_id is None:
                    session_id = entry.get("sessionId", filepath.stem)

                entries.append(entry)
    except OSError as e:
        log.warning("Cannot read %s: %s", filepath, e)
        return None

    if not entries:
        return None

    # Build turns, combining consecutive assistant messages into single turns
    turns: list[Turn] = []
    pending_assistant_texts: list[str] = []
    pending_thinking_blocks: list[ThinkingBlock] = []
    pending_sub_agent_refs: list[SubAgentRef] = []
    last_assistant_timestamp: str = ""

    # Track pending tool_use blocks to correlate with tool_result (TASK-003, TASK-005)
    pending_task_tool_uses: dict[str, dict] = {}
    pending_ask_tool_uses: dict[str, dict] = {}

    for entry in entries:
        msg = entry.get("message") or {}
        if not isinstance(msg, dict):
            msg = {}
        role = msg.get("role", entry.get("type"))
        content = msg.get("content", "")
        timestamp = entry.get("timestamp", "")

        if role == "user":
            # Extract SubAgentRef from Task tool_result BEFORE skip checks (TASK-003)
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        tool_use_id = block.get("tool_use_id", "")

                        # Check for Task tool_result
                        if tool_use_id in pending_task_tool_uses:
                            task_info = pending_task_tool_uses.pop(tool_use_id)
                            tool_result_meta = entry.get("toolUseResult", {})
                            agent_id = tool_result_meta.get("agentId", "")

                            if agent_id and validate_agent_id(agent_id):
                                summary_parts = []
                                result_content = block.get("content", [])
                                if isinstance(result_content, list):
                                    for part in result_content:
                                        if (
                                            isinstance(part, dict)
                                            and part.get("type") == "text"
                                        ):
                                            text = part.get("text", "")
                                            if not text.startswith("agentId:"):
                                                summary_parts.append(text)
                                summary = "\n".join(summary_parts)

                                sub_agent_ref = SubAgentRef(
                                    agent_id=agent_id,
                                    subagent_type=task_info["subagent_type"],
                                    description=task_info["description"],
                                    summary=summary,
                                    duration_ms=tool_result_meta.get("totalDurationMs"),
                                    tool_use_count=tool_result_meta.get(
                                        "totalToolUseCount"
                                    ),
                                    transcript_path=None,
                                )
                                # Attach to pending (will be flushed with next real assistant turn)
                                pending_sub_agent_refs.append(sub_agent_ref)

                        # Check for AskUserQuestion tool_result (TASK-005 - placeholder)
                        if tool_use_id in pending_ask_tool_uses:
                            pending_ask_tool_uses.pop(tool_use_id)
                            log.debug(
                                "AskUserQuestion tool_result found but parsing not implemented"
                            )

            # Skip tool results and other internal messages (don't add them as turns)
            if isinstance(content, list):
                has_tool_result_only = all(
                    isinstance(block, dict)
                    and block.get("type") in ("tool_result", "file_history_snapshot")
                    for block in content
                )
                if has_tool_result_only:
                    continue

            # Skip command metadata and CLI output (e.g., /exit, <local-command-stdout>)
            if isinstance(content, str):
                stripped = content.strip()
                if stripped.startswith("<command-") or stripped.startswith(
                    "<local-command-"
                ):
                    continue

            # This is a real user message — flush pending assistant data first
            if pending_assistant_texts:
                combined = "".join(pending_assistant_texts)
                if combined.strip():
                    turns.append(
                        Turn(
                            role="assistant",
                            text=combined,
                            timestamp=last_assistant_timestamp,
                            thinking_blocks=pending_thinking_blocks.copy(),
                            sub_agent_refs=pending_sub_agent_refs.copy(),
                        )
                    )
                pending_assistant_texts = []
                pending_thinking_blocks = []
                pending_sub_agent_refs = []
                last_assistant_timestamp = ""

            if isinstance(content, str) and content.strip():
                turns.append(Turn(role="user", text=content, timestamp=timestamp))
            elif isinstance(content, list):
                text = _extract_text(content)
                if text.strip():
                    turns.append(Turn(role="user", text=text, timestamp=timestamp))

        elif role == "assistant":
            # Extract text and thinking blocks from content (TASK-002)
            text_parts = []
            thinking_blocks = []

            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        block_type = block.get("type")

                        if block_type == "text":
                            text_parts.append(block.get("text", ""))

                        elif block_type == "thinking":
                            thinking_text = block.get("thinking", "")
                            if thinking_text:
                                thinking_blocks.append(
                                    ThinkingBlock(text=thinking_text)
                                )
                                log.debug(
                                    "Extracted thinking block (%d chars)",
                                    len(thinking_text),
                                )

                        # Track Task tool_use blocks (TASK-003)
                        elif block_type == "tool_use":
                            tool_name = block.get("name")
                            tool_use_id = block.get("id", "")

                            if tool_name == "Task" and tool_use_id:
                                inp = block.get("input", {})
                                pending_task_tool_uses[tool_use_id] = {
                                    "subagent_type": inp.get("subagent_type", ""),
                                    "description": inp.get("description", ""),
                                }

                            # Track AskUserQuestion tool_use blocks (TASK-005 - placeholder)
                            elif tool_name == "AskUserQuestion" and tool_use_id:
                                inp = block.get("input", {})
                                pending_ask_tool_uses[tool_use_id] = {
                                    "questions": inp.get("questions", []),
                                }

            text = "\n".join(text_parts) if text_parts else ""
            if text:
                pending_assistant_texts.append(text)
                pending_thinking_blocks.extend(thinking_blocks)
                if not last_assistant_timestamp:
                    last_assistant_timestamp = timestamp

    # Flush remaining assistant data
    if pending_assistant_texts:
        combined = "".join(pending_assistant_texts)
        if combined.strip():
            turns.append(
                Turn(
                    role="assistant",
                    text=combined,
                    timestamp=last_assistant_timestamp,
                    thinking_blocks=pending_thinking_blocks.copy(),
                    sub_agent_refs=pending_sub_agent_refs.copy(),
                )
            )

    if not turns:
        return None

    return Session(
        session_id=session_id or filepath.stem,
        turns=turns,
        filepath=filepath,
        progress_entries=progress_entries_by_parent,
    )


def discover_sessions(
    project_dir: Path,
    start_time: float,
    session_id: str | None = None,
) -> list[Session]:
    """Find and parse JSONL session files."""
    if not project_dir.is_dir():
        log.warning("Project directory not found: %s", project_dir)
        return []

    # Security check (SEC-006): verify path is under CLAUDE_DIR
    try:
        project_dir.resolve().relative_to(CLAUDE_DIR.resolve())
    except ValueError:
        log.warning("Project directory %s is not under %s", project_dir, CLAUDE_DIR)
        return []

    sessions = []
    for jsonl_file in sorted(project_dir.glob("*.jsonl")):
        # Filter by modification time (post-hoc discovery)
        if start_time > 0 and jsonl_file.stat().st_mtime < start_time:
            continue

        session = parse_session(jsonl_file)
        if session is None:
            continue

        # Filter by session ID if requested
        if session_id and session.session_id != session_id:
            continue

        sessions.append(session)

    return sessions
