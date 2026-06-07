"""Turn continuation — handles long response truncation and auto-continue."""


def should_persist_user_message(metadata: dict | None) -> bool:
    """Check if user message should be persisted early."""
    if not metadata:
        return True
    return not metadata.get("_internal_continuation", False)


def internal_continuation_pending(metadata: dict | None) -> bool:
    """Check if internal continuation is pending."""
    if not metadata:
        return False
    return metadata.get("_internal_continuation", False)
