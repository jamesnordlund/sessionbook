"""HTML generation for sessionbook sessions."""

import html
import logging
import os
import tempfile
from datetime import datetime
from pathlib import Path

from markdown_it import MarkdownIt
from pygments import highlight
from pygments.lexers import get_lexer_by_name, ClassNotFound
from pygments.formatters import HtmlFormatter

from sessionbook.jsonl import Session, Turn, ThinkingBlock, UserChoice, SubAgentRef
from sessionbook.util import validate_agent_id as _validate_agent_id

log = logging.getLogger("sessionbook")


def highlight_code(code, lang, attrs):
    """Highlight code using Pygments."""
    if not lang:
        return None
    try:
        lexer = get_lexer_by_name(lang)
        formatter = HtmlFormatter(nowrap=True)
        return highlight(code, lexer, formatter)
    except ClassNotFound:
        return None


# Initialize markdown renderer with GFM-like options
# html: False ensures user-provided HTML tags are escaped for security
md = MarkdownIt(
    "js-default",
    {"html": False, "typographer": True, "linkify": True, "highlight": highlight_code},
)

# Generate Pygments CSS for the 'friendly' style
PYGMENTS_CSS = HtmlFormatter(style="friendly").get_style_defs(".highlight")

CSS_TEMPLATE = f"""
/* Reset and base styles */
* {{
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}}

body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    line-height: 1.6;
    color: #202124;
    background: #f8f9fa;
    padding: 20px;
}}

/* Container */
.container {{
    max-width: 900px;
    margin: 0 auto;
    background: white;
    padding: 40px;
    border-radius: 8px;
    box-shadow: 0 1px 3px rgba(60,64,67,0.15), 0 4px 8px rgba(60,64,67,0.08);
}}

/* Session header */
.session-header {{
    border-bottom: 2px solid #e8eaed;
    padding-bottom: 20px;
    margin-bottom: 40px;
}}

.session-header h1 {{
    font-size: 28px;
    font-weight: 500;
    color: #202124;
    margin-bottom: 8px;
}}

.session-meta {{
    font-size: 14px;
    color: #5f6368;
    display: flex;
    gap: 16px;
}}

.session-id {{
    font-family: 'Monaco', 'Menlo', 'Consolas', monospace;
    background: #f1f3f4;
    padding: 2px 6px;
    border-radius: 3px;
}}

/* Turn styles */
.turn {{
    margin-bottom: 24px;
    padding: 20px;
    border-radius: 8px;
    border-left: 4px solid;
}}

.turn-user {{
    background: #e8f0fe;
    border-left-color: #1a73e8;
}}

.turn-assistant {{
    background: #f8f9fa;
    border-left-color: #34a853;
}}

.turn-meta {{
    font-size: 12px;
    color: #5f6368;
    margin-bottom: 12px;
    display: flex;
    gap: 12px;
}}

.turn-role {{
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}}

.turn-content {{
    font-size: 15px;
    line-height: 1.6;
    color: #202124;
    word-wrap: break-word;
}}

/* Markdown styling within turn-content and thinking-content */
.turn-content p, .thinking-content p {{
    margin-bottom: 12px;
}}

.turn-content p:last-child, .thinking-content p:last-child {{
    margin-bottom: 0;
}}

.turn-content h1, .turn-content h2, .turn-content h3, 
.thinking-content h1, .thinking-content h2, .thinking-content h3 {{
    margin-top: 16px;
    margin-bottom: 8px;
    font-weight: 600;
}}

.turn-content h1, .thinking-content h1 {{ font-size: 1.4em; }}
.turn-content h2, .thinking-content h2 {{ font-size: 1.25em; }}
.turn-content h3, .thinking-content h3 {{ font-size: 1.1em; }}

.turn-content code, .thinking-content code {{
    font-family: 'Monaco', 'Menlo', 'Consolas', monospace;
    background: rgba(0,0,0,0.05);
    padding: 2px 4px;
    border-radius: 3px;
    font-size: 0.9em;
}}

.turn-content pre, .thinking-content pre {{
    background: #202124;
    color: #f8f9fa;
    padding: 16px;
    border-radius: 6px;
    margin: 12px 0;
    overflow-x: auto;
}}

.turn-content pre code, .thinking-content pre code {{
    background: transparent;
    color: inherit;
    padding: 0;
    font-size: 0.85em;
}}

.turn-content ul, .turn-content ol, 
.thinking-content ul, .thinking-content ol {{
    margin: 12px 0;
    padding-left: 24px;
}}

.turn-content li, .thinking-content li {{
    margin-bottom: 4px;
}}

/* Pygments Syntax Highlighting */
{PYGMENTS_CSS}

/* Thinking blocks */
.thinking-block {{
    margin-top: 16px;
    border: 1px solid #dadce0;
    border-radius: 6px;
    background: #fefefe;
}}

.thinking-block summary {{
    padding: 10px 14px;
    cursor: pointer;
    font-weight: 500;
    font-size: 13px;
    color: #5f6368;
    user-select: none;
    display: flex;
    align-items: center;
}}

.thinking-block summary:hover {{
    background: #f8f9fa;
}}

.thinking-block summary::before {{
    content: "▸ ";
    display: inline-block;
    margin-right: 6px;
    transition: transform 0.2s;
}}

.thinking-block[open] summary::before {{
    transform: rotate(90deg);
}}

.thinking-content {{
    padding: 14px;
    font-size: 13px;
    line-height: 1.5;
    border-top: 1px solid #e8eaed;
    color: #3c4043;
    background: #fafafa;
}}

/* User choice card */
.choice-card {{
    margin-top: 16px;
    padding: 16px;
    border: 2px solid #f9ab00;
    border-radius: 6px;
    background: #fef7e0;
}}

.choice-question {{
    font-weight: 600;
    font-size: 14px;
    margin-bottom: 12px;
    color: #e37400;
}}

.choice-options {{
    list-style: none;
    margin: 0;
    padding: 0;
}}

.choice-option {{
    padding: 8px 12px;
    margin: 6px 0;
    border-radius: 4px;
    background: white;
    font-size: 14px;
    border: 1px solid #f9ab00;
}}

.choice-selected {{
    background: #fbbc04;
    font-weight: 600;
    border-color: #e37400;
    color: #3c4043;
}}

.choice-selected::before {{
    content: "✓ ";
    color: #e37400;
    font-weight: bold;
}}

/* Sub-agent card */
.sub-agent-card {{
    margin-top: 16px;
    padding: 16px;
    border: 2px solid #8430ce;
    border-radius: 6px;
    background: #f3e8fd;
}}

.sub-agent-header {{
    font-weight: 600;
    font-size: 14px;
    margin-bottom: 8px;
    color: #6a1b9a;
    display: flex;
    align-items: center;
    gap: 8px;
}}

.sub-agent-type {{
    font-family: 'Monaco', 'Menlo', 'Consolas', monospace;
    background: #e1bee7;
    padding: 2px 6px;
    border-radius: 3px;
    font-size: 12px;
}}

.sub-agent-meta {{
    font-size: 12px;
    color: #7b1fa2;
    margin-bottom: 10px;
}}

.sub-agent-summary {{
    font-size: 13px;
    color: #4a148c;
    margin-bottom: 12px;
    white-space: pre-wrap;
    line-height: 1.5;
}}

.sub-agent-link {{
    display: inline-block;
    padding: 8px 16px;
    background: #8430ce;
    color: white;
    text-decoration: none;
    border-radius: 4px;
    font-size: 13px;
    font-weight: 500;
    transition: background 0.2s;
}}

.sub-agent-link:hover {{
    background: #6a1b9a;
}}

.sub-agent-broken-link {{
    font-size: 13px;
    color: #9e9e9e;
    font-style: italic;
}}

/* Responsive design */
@media (max-width: 768px) {{
    body {{
        padding: 12px;
    }}

    .container {{
        padding: 20px;
    }}

    .turn {{
        padding: 16px;
    }}
}}
"""


def _escape_html(text: str) -> str:
    """Escape HTML special characters in text.

    Args:
        text: Raw text that may contain <, >, &, ", '

    Returns:
        Text with HTML entities escaped
    """
    if not isinstance(text, str):
        text = str(text)
    return html.escape(text, quote=True)


def _render_markdown(text: str) -> str:
    """Render markdown text to HTML.

    Args:
        text: Markdown string

    Returns:
        HTML string
    """
    if not isinstance(text, str):
        text = str(text)
    return md.render(text)


def _render_thinking_block(thinking_block: ThinkingBlock) -> str:
    """Render a thinking block as HTML details element.

    Args:
        thinking_block: ThinkingBlock object with text

    Returns:
        HTML string for <details class="thinking-block">...</details>
        (collapsed by default, no 'open' attribute)
    """
    content = _render_markdown(thinking_block.text)
    return (
        '            <details class="thinking-block">\n'
        "                <summary>Thinking</summary>\n"
        f'                <div class="thinking-content">{content}</div>\n'
        "            </details>"
    )


def _render_user_choice(user_choice: UserChoice) -> str:
    """Render a user choice interaction as HTML card.

    Args:
        user_choice: UserChoice object with question, options, selected_index

    Returns:
        HTML string for <div class="choice-card">...</div>
        with question, options list, and selected option highlighted
    """
    question = _escape_html(user_choice.question)
    parts = [
        '            <div class="choice-card">',
        f'                <div class="choice-question">{question}</div>',
        '                <ul class="choice-options">',
    ]

    for i, option in enumerate(user_choice.options):
        escaped_option = _escape_html(option)
        if i == user_choice.selected_index:
            parts.append(
                f'                    <li class="choice-option choice-selected">{escaped_option}</li>'
            )
        else:
            parts.append(
                f'                    <li class="choice-option">{escaped_option}</li>'
            )

    parts.extend(
        [
            "                </ul>",
            "            </div>",
        ]
    )

    log.debug("Rendered user choice: %s", question)
    return "\n".join(parts)


def _render_sub_agent_card(sub_agent_ref: SubAgentRef) -> str:
    """Render a sub-agent reference as HTML card with link.

    Args:
        sub_agent_ref: SubAgentRef with agent_id, summary, transcript_path

    Returns:
        HTML string for <div class="sub-agent-card">...</div>
        with summary and hyperlink if transcript_path is not None,
        otherwise with broken-link indicator
    """
    agent_id = _escape_html(sub_agent_ref.agent_id)
    subagent_type = _escape_html(sub_agent_ref.subagent_type)
    description = _escape_html(sub_agent_ref.description)

    # Truncate summary to 500 chars for card display
    summary_text = sub_agent_ref.summary
    if len(summary_text) > 500:
        summary_text = summary_text[:500] + "..."
    summary = _escape_html(summary_text)

    parts = [
        '            <div class="sub-agent-card">',
        '                <div class="sub-agent-header">',
        f'                    <span class="sub-agent-type">{subagent_type}</span>',
        f"                    <span>{description}</span>",
        "                </div>",
    ]

    # Add metadata if available
    meta_parts = []
    if sub_agent_ref.duration_ms is not None:
        duration_sec = sub_agent_ref.duration_ms / 1000
        meta_parts.append(f"Duration: {duration_sec:.1f}s")
    if sub_agent_ref.tool_use_count is not None:
        meta_parts.append(f"Tool uses: {sub_agent_ref.tool_use_count}")

    if meta_parts:
        meta_text = _escape_html(" • ".join(meta_parts))
        parts.append(f'                <div class="sub-agent-meta">{meta_text}</div>')

    parts.append(f'                <div class="sub-agent-summary">{summary}</div>')

    if sub_agent_ref.transcript_path:
        link = _escape_html(sub_agent_ref.transcript_path)
        parts.append(
            f'                <a href="{link}" class="sub-agent-link">View transcript →</a>'
        )
    else:
        parts.append(
            '                <span class="sub-agent-broken-link">Transcript not available</span>'
        )

    parts.append("            </div>")

    log.debug("Rendered sub-agent card: %s", agent_id)
    return "\n".join(parts)


def _render_turn_html(turn: Turn, turn_index: int) -> str:
    """Render a single Turn as HTML article element.

    Args:
        turn: Turn object with role, text, timestamp, and optional metadata
        turn_index: Zero-based index of turn in session (for element IDs)

    Returns:
        HTML string for <article class="turn turn-{role}">...</article>
    """
    role_class = f"turn-{turn.role}"
    role_label = turn.role.capitalize()
    timestamp = _escape_html(turn.timestamp)
    content = _render_markdown(turn.text)

    parts = [
        f'        <article class="turn {role_class}" id="turn-{turn_index}">',
        '            <div class="turn-meta">',
        f'                <span class="turn-role">{role_label}</span>',
        f'                <span class="turn-timestamp">{timestamp}</span>',
        "            </div>",
        f'            <div class="turn-content">{content}</div>',
    ]

    # Render thinking blocks
    for thinking_block in turn.thinking_blocks:
        parts.append(_render_thinking_block(thinking_block))
        log.debug("Rendered thinking block: %s...", thinking_block.text[:50])

    # Render user choice if present
    if turn.user_choice:
        parts.append(_render_user_choice(turn.user_choice))

    # Render sub-agent cards
    for sub_agent_ref in turn.sub_agent_refs:
        if _validate_agent_id(sub_agent_ref.agent_id):
            parts.append(_render_sub_agent_card(sub_agent_ref))
        else:
            log.warning(
                "Skipping sub-agent card for invalid ID: %s", sub_agent_ref.agent_id
            )

    parts.append("        </article>")
    return "\n".join(parts)


def build_html(session: Session) -> str:
    """Generate complete HTML document from Session.

    Args:
        session: Session object with turns and metadata

    Returns:
        Complete HTML5 document as string with inline CSS

    Notes:
        - All user-provided text is HTML-escaped
        - CSS is inlined in <style> block
        - No external resource dependencies
        - Includes <meta> tag with session_id and conversion timestamp
    """
    session_id = _escape_html(session.session_id)
    conversion_time = datetime.now().isoformat()

    # Extract date from first turn for display
    session_date = "Unknown date"
    if session.turns:
        first_timestamp = session.turns[0].timestamp
        try:
            dt = datetime.fromisoformat(first_timestamp.replace("Z", "+00:00"))
            session_date = dt.strftime("%Y-%m-%d %H:%M:%S")
        except (ValueError, AttributeError):
            pass

    # Build HTML header
    html_parts = [
        "<!DOCTYPE html>",
        '<html lang="en">',
        "<head>",
        '    <meta charset="UTF-8">',
        '    <meta name="viewport" content="width=device-width, initial-scale=1.0">',
        f'    <meta name="sessionbook-session-id" content="{session_id}">',
        f'    <meta name="sessionbook-converted" content="{conversion_time}">',
        f"    <title>Claude Code Session - {session_id}</title>",
        "    <style>",
        CSS_TEMPLATE,
        "    </style>",
        "</head>",
        "<body>",
        '    <div class="container">',
        '        <header class="session-header">',
        "            <h1>Claude Code Session</h1>",
        '            <div class="session-meta">',
        f'                <span class="session-id">{session_id}</span>',
        f'                <span class="session-date">{_escape_html(session_date)}</span>',
        "            </div>",
        "        </header>",
    ]

    # Render turns
    for i, turn in enumerate(session.turns):
        html_parts.append(_render_turn_html(turn, i))

    # Close HTML
    html_parts.extend(
        [
            "    </div>",
            "</body>",
            "</html>",
        ]
    )

    return "\n".join(html_parts)


def _compute_filename(session: Session) -> str:
    """Compute HTML filename from session timestamp.

    Args:
        session: Session with turns list

    Returns:
        Filename string in format "YYYY-MM-DDTHH-MM-SS.html"

    Notes:
        Uses last turn timestamp, converts to local time.
        Falls back to current time if timestamp is malformed.
    """
    last_ts = session.turns[-1].timestamp if session.turns else ""
    if last_ts:
        try:
            dt = datetime.fromisoformat(last_ts.replace("Z", "+00:00"))
            dt_local = dt.astimezone()
        except (ValueError, OSError):
            log.warning("Malformed timestamp %s, using current time", last_ts)
            dt_local = datetime.now()
    else:
        dt_local = datetime.now()
    return dt_local.strftime("%Y-%m-%dT%H-%M-%S") + ".html"


def _existing_session_ids(output_dir: Path) -> set[str]:
    """Scan .sessionbook/*.html files and extract session IDs from meta tags.

    Args:
        output_dir: Directory containing HTML files

    Returns:
        Set of session IDs that have been saved
    """
    ids: set[str] = set()
    if not output_dir.is_dir():
        return ids

    for html_file in output_dir.glob("*.html"):
        try:
            with open(html_file, encoding="utf-8") as f:
                # Read first 50 lines to find meta tag (it's in <head>)
                for _ in range(50):
                    line = f.readline()
                    if not line:
                        break
                    # Look for sessionbook-session-id meta tag
                    if 'name="sessionbook-session-id"' in line and 'content="' in line:
                        # Extract content value
                        start = line.find('content="') + len('content="')
                        end = line.find('"', start)
                        if start > 0 and end > start:
                            session_id = line[start:end]
                            ids.add(session_id)
                            break
        except OSError:
            # Skip files that can't be read
            pass

    return ids


def save_html(session: Session, output_dir: Path) -> Path | None:
    """Convert a Session to HTML and write atomically.

    Args:
        session: Session object with turns and metadata
        output_dir: Directory to write HTML file (typically .sessionbook/)

    Returns:
        Path to written HTML file, or None if session is empty

    Side effects:
        - Creates output_dir if not exists (mode 0o755)
        - Writes HTML file atomically (tempfile + rename)
        - Sets file permissions to 0o644
        - Logs info message with filename, turn count, thinking block count

    Error handling:
        - Returns None if session.turns is empty
        - Returns None if output_dir cannot be created (logs error)
        - Returns None if file write fails (logs error, cleans up tempfile)
    """
    if not session.turns:
        log.info("Session %s has no extractable turns, skipping", session.session_id)
        return None

    # Ensure output directory exists
    try:
        output_dir.mkdir(mode=0o755, parents=True, exist_ok=True)
    except OSError as e:
        log.error("Cannot create %s: %s", output_dir, e)
        return None

    # Generate HTML
    html_content = build_html(session)

    # Compute filename with collision handling
    filename = _compute_filename(session)
    final_path = output_dir / filename

    if final_path.exists():
        stem = final_path.stem
        suffix_num = 1
        while final_path.exists():
            final_path = output_dir / f"{stem}-{suffix_num}.html"
            suffix_num += 1
            if suffix_num > 1000:
                log.error("Too many filename collisions for %s", filename)
                return None
        log.debug("Filename collision resolved: %s → %s", filename, final_path.name)

    # Atomic write
    try:
        fd, tmp_path = tempfile.mkstemp(dir=str(output_dir), suffix=".html.tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(html_content)
            os.chmod(tmp_path, 0o644)
            os.rename(tmp_path, str(final_path))
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
    except OSError as e:
        log.error("Failed to write HTML: %s", e)
        return None

    # Count metadata for logging
    thinking_count = sum(len(t.thinking_blocks) for t in session.turns)
    sub_agent_count = sum(len(t.sub_agent_refs) for t in session.turns)
    log.info(
        "Saved %s (%d turns, %d thinking blocks, %d sub-agents)",
        final_path.name,
        len(session.turns),
        thinking_count,
        sub_agent_count,
    )

    return final_path
