"""Common utilities for Swarm."""

from swarm.utils.tokens import estimate_tokens, estimate_message_tokens


def extract_chat_id(session_key: str) -> str:
    """Extract chat_id from a session key of the form 'prefix:chat_id'.

    Returns the full key if no colon separator is found.
    """
    return session_key.split(":", 1)[1] if ":" in session_key else session_key
