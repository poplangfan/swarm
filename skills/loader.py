"""Markdown Skills loader — frontmatter-based skill definitions.

Skills are Markdown files with YAML frontmatter:

---
name: my-skill
description: What this skill does
always: false
---

# Skill Content
...
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import structlog
import yaml

logger = structlog.get_logger(__name__)

FRONTMATTER_RE = re.compile(r"^---\s*\r?\n(.*?)\r?\n---\s*\r?\n", re.DOTALL)


@dataclass
class Skill:
    """A loaded skill definition."""

    name: str
    description: str = ""
    content: str = ""
    always: bool = False
    permissions: list[str] = field(default_factory=list)
    path: Path | None = None


class SkillsLoader:
    """Loads and manages Markdown skills from a directory.

    Skills directory structure:
        skills/
        ├── my-skill/
        │   └── SKILL.md
        ├── another-skill/
        │   └── SKILL.md

    Always-active skills are injected into every system prompt.
    Other skills are available on-demand via the skill catalog.
    """

    def __init__(self, skills_dir: Path, disabled_skills: set[str] | None = None):
        self._skills_dir = Path(skills_dir)
        existed_before = self._skills_dir.exists()
        self._skills_dir.mkdir(parents=True, exist_ok=True)
        self._disabled = disabled_skills or set()
        self._skills: dict[str, Skill] = {}
        self._always_skills: list[str] = []
        self._load_all()

        # Warn if we created a new directory or loaded no skills from a non-empty dir
        if not existed_before:
            logger.warning(
                "skills_dir_created",
                path=str(self._skills_dir),
                hint="Directory did not exist; check skills path config",
            )
        elif self.skill_count == 0:
            has_subdirs = any(p.is_dir() for p in self._skills_dir.iterdir())
            if has_subdirs:
                # Directory has subdirectories but no valid SKILL.md files found
                logger.warning(
                    "skills_dir_no_valid_skills",
                    path=str(self._skills_dir),
                    hint="Directory exists but no valid SKILL.md files found",
                )

    def _load_all(self) -> None:
        """Scan the skills directory and load all skills."""
        for skill_dir in self._skills_dir.iterdir():
            if not skill_dir.is_dir():
                continue
            skill_file = skill_dir / "SKILL.md"
            if not skill_file.exists():
                continue
            try:
                skill = self._load_skill_file(skill_file)
                if skill and skill.name not in self._disabled:
                    self._skills[skill.name] = skill
                    if skill.always:
                        self._always_skills.append(skill.name)
                    logger.debug("skill_loaded", name=skill.name, always=skill.always)
            except Exception as e:
                logger.warning("skill_load_error", path=str(skill_file), error=str(e))

    def _load_skill_file(self, path: Path) -> Skill | None:
        """Parse a SKILL.md file into a Skill object."""
        text = path.read_text(encoding="utf-8")
        match = FRONTMATTER_RE.match(text)
        if not match:
            logger.warning("skill_no_frontmatter", path=str(path))
            return None

        meta = yaml.safe_load(match.group(1)) or {}
        content = text[match.end() :].strip()

        return Skill(
            name=meta.get("name", path.parent.name),
            description=meta.get("description", ""),
            content=content,
            always=meta.get("always", False),
            permissions=meta.get("permissions", []),
            path=path,
        )

    def get_always_skills(self) -> list[str]:
        """Return names of always-active skills."""
        return list(self._always_skills)

    def get_skill(self, name: str) -> Skill | None:
        """Get a skill by name."""
        return self._skills.get(name)

    def get_skill_content(self, name: str) -> str:
        """Get the content of a skill by name."""
        skill = self._skills.get(name)
        return skill.content if skill else ""

    def load_skills_for_context(self, names: list[str]) -> str:
        """Load and concatenate skill contents for context injection."""
        parts = []
        for name in names:
            skill = self._skills.get(name)
            if skill:
                parts.append(f"## Skill: {skill.name}\n{skill.content}")
        return "\n\n".join(parts)

    def build_skills_summary(self, exclude: set[str] | None = None) -> str:
        """Build a summary of available (non-always) skills."""
        exclude = exclude or set()
        available = [
            s
            for name, s in self._skills.items()
            if name not in exclude and name not in self._always_skills
        ]
        if not available:
            return ""
        lines = ["# Available Skills", ""]
        for s in available:
            lines.append(f"- **{s.name}**: {s.description}")
        return "\n".join(lines)

    def list_skills(self) -> list[dict[str, Any]]:
        """List all loaded skills with metadata."""
        return [
            {
                "name": s.name,
                "description": s.description,
                "always": s.always,
                "permissions": s.permissions,
            }
            for s in self._skills.values()
        ]

    @property
    def skill_count(self) -> int:
        return len(self._skills)

    @property
    def always_count(self) -> int:
        return len(self._always_skills)
