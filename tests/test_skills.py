"""Tests for skills loader."""

import tempfile
from pathlib import Path
from swarm.skills.loader import SkillsLoader, Skill


class TestSkillsLoader:
    def test_loads_skill_from_directory(self):
        with tempfile.TemporaryDirectory() as d:
            skill_dir = Path(d) / "my-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("""---
name: test-skill
description: A test skill
always: false
---

# Test Skill
This is the skill content.
""")
            loader = SkillsLoader(Path(d))
            assert loader.skill_count == 1
            skill = loader.get_skill("test-skill")
            assert skill is not None
            assert skill.description == "A test skill"
            assert "This is the skill content" in skill.content

    def test_always_skill(self):
        with tempfile.TemporaryDirectory() as d:
            skill_dir = Path(d) / "always-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("""---
name: always-on
description: Always active
always: true
---

# Always On
I am always active.
""")
            loader = SkillsLoader(Path(d))
            assert loader.always_count == 1
            assert "always-on" in loader.get_always_skills()

    def test_disabled_skill_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            skill_dir = Path(d) / "disabled-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("""---
name: disabled-one
description: Should be skipped
---
Content
""")
            loader = SkillsLoader(Path(d), disabled_skills={"disabled-one"})
            assert loader.skill_count == 0

    def test_skills_summary(self):
        with tempfile.TemporaryDirectory() as d:
            for name in ["skill-a", "skill-b", "always-c"]:
                sd = Path(d) / name
                sd.mkdir()
                always = "true" if name == "always-c" else "false"
                (sd / "SKILL.md").write_text(f"""---
name: {name}
description: Description for {name}
always: {always}
---
Content for {name}
""")
            loader = SkillsLoader(Path(d))
            summary = loader.build_skills_summary()
            assert "skill-a" in summary
            assert "skill-b" in summary
            assert "always-c" not in summary  # Always skills excluded from summary

    def test_load_content_for_context(self):
        with tempfile.TemporaryDirectory() as d:
            sd = Path(d) / "ctx-skill"
            sd.mkdir()
            (sd / "SKILL.md").write_text("""---
name: ctx-skill
description: Context skill
---
Context content here.
""")
            loader = SkillsLoader(Path(d))
            ctx = loader.load_skills_for_context(["ctx-skill"])
            assert "Context content here" in ctx

    def test_empty_directory(self):
        with tempfile.TemporaryDirectory() as d:
            loader = SkillsLoader(Path(d))
            assert loader.skill_count == 0

    def test_list_skills(self):
        with tempfile.TemporaryDirectory() as d:
            sd = Path(d) / "list-skill"
            sd.mkdir()
            (sd / "SKILL.md").write_text("""---
name: list-skill
description: For listing
---
Content
""")
            loader = SkillsLoader(Path(d))
            skills = loader.list_skills()
            assert len(skills) == 1
            assert skills[0]["name"] == "list-skill"
