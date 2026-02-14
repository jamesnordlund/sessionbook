"""Shared utilities for sessionbook."""

import logging
import re

log = logging.getLogger("sessionbook")

AGENT_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")


def validate_agent_id(agent_id: str) -> bool:
    """Validate sub-agent identifier against security pattern.

    Args:
        agent_id: String to validate

    Returns:
        True if agent_id matches ^[a-zA-Z0-9_-]+$, False otherwise

    Security:
        Prevents path traversal attacks (SEC-002, SEC-003)
    """
    if not agent_id:
        return False
    if not AGENT_ID_PATTERN.match(agent_id):
        log.warning("Invalid agent_id: %s (path traversal attempt?)", agent_id)
        return False
    return True
