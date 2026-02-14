#!/bin/sh
# Mock claude script that writes JSONL then exits with code 42 (TASK-013).
# Writes a valid 4-entry JSONL session file to the directory given as $1.
# Usage: mock_claude_exit42.sh <project-dir>

OUTPUT_DIR="$1"

if [ -z "$OUTPUT_DIR" ]; then
    echo "Usage: mock_claude_exit42.sh <project-dir>" >&2
    exit 1
fi

mkdir -p "$OUTPUT_DIR"

cat > "$OUTPUT_DIR/session.jsonl" <<'JSONL'
{"type": "user", "sessionId": "sess-exit42", "timestamp": "2026-02-07T11:00:00Z", "message": {"role": "user", "content": "Hello before exit 42"}}
{"type": "assistant", "sessionId": "sess-exit42", "timestamp": "2026-02-07T11:00:01Z", "requestId": "req-e1", "message": {"role": "assistant", "content": [{"type": "text", "text": "Response before exit 42."}]}}
{"type": "user", "sessionId": "sess-exit42", "timestamp": "2026-02-07T11:00:02Z", "message": {"role": "user", "content": "Another prompt before exit 42"}}
{"type": "assistant", "sessionId": "sess-exit42", "timestamp": "2026-02-07T11:00:03Z", "requestId": "req-e2", "message": {"role": "assistant", "content": [{"type": "text", "text": "Another response before exit 42."}]}}
JSONL

exit 42
