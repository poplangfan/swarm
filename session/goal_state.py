"""Sustained goal state tracking — for long-running objectives across turns."""


def goal_state_runtime_lines(metadata: dict | None) -> list[str]:
    """Extract goal state as runtime context lines for LLM."""
    if not metadata or "goal" not in metadata:
        return []
    goal = metadata["goal"]
    return [f"Active Goal: {goal.get('objective', '')}"]


def sustained_goal_active(metadata: dict | None) -> bool:
    """Check if a sustained goal is active."""
    if not metadata:
        return False
    return metadata.get("goal", {}).get("active", False)
