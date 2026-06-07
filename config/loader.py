"""Configuration loader: YAML parsing with ${ENV_VAR} substitution."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml

from config.schema import SwarmConfig

_ENV_VAR_RE = re.compile(r"\$\{([^}]+)\}")


def _resolve_env_vars(value: Any) -> Any:
    """Recursively substitute ${ENV_VAR} placeholders in strings."""
    if isinstance(value, str):

        def _replace(match: re.Match) -> str:
            var = match.group(1)
            default = None
            if ":-" in var:
                var, default = var.split(":-", 1)
            result = os.environ.get(var.strip())
            if result is not None:
                return result
            if default is not None:
                return default.strip()
            return match.group(0)

        return _ENV_VAR_RE.sub(_replace, value)
    elif isinstance(value, dict):
        return {k: _resolve_env_vars(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [_resolve_env_vars(item) for item in value]
    return value


def load_config(path: str | Path | None = None) -> SwarmConfig:
    """Load and validate configuration from a YAML file.

    Searches in order:
    1. Explicit path argument
    2. SWARM_CONFIG environment variable
    3. ./config.yaml
    4. ~/.swarm/config.yaml
    """
    if path is not None:
        config_path = Path(path)
    elif env_path := os.environ.get("SWARM_CONFIG"):
        config_path = Path(env_path)
    else:
        candidates = [
            Path.cwd() / "config.yaml",
            Path.home() / ".swarm" / "config.yaml",
        ]
        for p in candidates:
            if p.exists():
                config_path = p
                break
        else:
            raise FileNotFoundError(
                "Config file not found. Searched: "
                + ", ".join(str(p) for p in candidates)
                + ". Copy config.yaml.example to config.yaml and fill in your values."
            )

    with open(config_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    if raw is None:
        raise ValueError(f"Config file {config_path} is empty")

    resolved = _resolve_env_vars(raw)
    return SwarmConfig.model_validate(resolved)
