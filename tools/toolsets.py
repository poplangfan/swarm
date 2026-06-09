"""Toolset definitions — group tools by capability domain.

Inspired by Hermes Agent's toolsets.py pattern:
- Each toolset is a named group that controls which tools are disclosed to the LLM
- DEFAULT_TOOLSETS defines what every session gets
- Platform-specific configs can add/remove toolsets
"""

from __future__ import annotations

# Toolset groups define which tools are available.
# Tools are registered with a toolset name; the agent loop filters
# get_definitions() to only include tools from enabled toolsets.
TOOLSETS: dict[str, dict] = {
    "core": {
        "description": "Core system tools: help, status, session management",
        "tools": ["system_command"],
    },
    "web": {
        "description": "Web search and content fetching",
        "tools": ["web_search", "web_fetch"],
    },
    "messaging": {
        "description": "Send messages, reactions, and media on Feishu",
        "tools": ["feishu_message"],
    },
    "feishu": {
        "description": "Feishu platform tools: files, docs, drives, auth",
        "tools": ["feishu_file", "feishu_auth"],
    },
    "cron": {
        "description": "Scheduled task management",
        "tools": ["cron_manage"],
    },
    "mcp": {
        "description": "MCP server-provided tools (dynamic)",
        "tools": [],
    },
    "plugin": {
        "description": "Plugin-provided tools (dynamic)",
        "tools": [],
    },
}

# Toolset descriptions for LLM context
TOOLSET_DESCRIPTIONS = {k: v["description"] for k, v in TOOLSETS.items()}

# Toolsets enabled by default for all sessions
DEFAULT_TOOLSETS = {"core", "web", "messaging", "feishu", "cron"}

# Toolsets that require explicit opt-in
OPT_IN_TOOLSETS = {"mcp", "plugin"}

# Allowed platforms per toolset (empty = all)
PLATFORM_ALLOWLIST: dict[str, set[str]] = {}


def resolve_toolset(name: str) -> str:
    """Normalize toolset name. Returns the canonical key if found, else the input."""
    if name in TOOLSETS:
        return name
    # Case-insensitive lookup
    for key in TOOLSETS:
        if key.lower() == name.lower():
            return key
    return name


def get_enabled_tools(
    enabled_toolsets: set[str] | None = None,
) -> set[str]:
    """Return the set of tool names enabled for the given toolsets."""
    if enabled_toolsets is None:
        enabled_toolsets = DEFAULT_TOOLSETS
    tools: set[str] = set()
    for ts_name in enabled_toolsets:
        ts = TOOLSETS.get(resolve_toolset(ts_name))
        if ts:
            tools.update(ts["tools"])
    return tools
