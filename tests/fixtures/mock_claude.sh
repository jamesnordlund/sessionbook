#!/bin/sh
# Mock claude script for integration testing (TASK-013).
# Writes a valid 4-entry JSONL session file to the directory given as $1.
# Usage: mock_claude.sh <project-dir>

OUTPUT_DIR="$1"

if [ -z "$OUTPUT_DIR" ]; then
    echo "Usage: mock_claude.sh <project-dir>" >&2
    exit 1
fi

mkdir -p "$OUTPUT_DIR"

cat > "$OUTPUT_DIR/session.jsonl" <<'JSONL'
{"type": "user", "sessionId": "sess-mock", "timestamp": "2026-02-07T10:00:00Z", "message": {"role": "user", "content": "Hello from mock"}}
{"type": "assistant", "sessionId": "sess-mock", "timestamp": "2026-02-07T10:00:01Z", "requestId": "req-m1", "message": {"role": "assistant", "content": [{"type": "text", "text": "Hi, I am the mock assistant."}]}}
{"type": "user", "sessionId": "sess-mock", "timestamp": "2026-02-07T10:00:02Z", "message": {"role": "user", "content": "Goodbye from mock"}}
{"type": "assistant", "sessionId": "sess-mock", "timestamp": "2026-02-07T10:00:03Z", "requestId": "req-m2", "message": {"role": "assistant", "content": [{"type": "text", "text": "Farewell from the mock assistant!"}]}}
JSONL

exit 0
