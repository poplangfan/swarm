# Skills Guide

Skills are Markdown files that define agent behaviors and knowledge — no code required.

## How Skills Work

Skills are loaded from the skills directory (or built-in) and injected into the LLM's system prompt. The LLM reads the skill content and follows the instructions.

```
Skills Directory:
skills/
├── base-assistant/
│   └── SKILL.md        ← Always active
├── calendar/
│   └── SKILL.md        ← Available on-demand
└── custom-skill/
    └── SKILL.md        ← Your custom skill
```

## Skill File Format

Each skill is a Markdown file with YAML frontmatter:

```markdown
---
name: my-skill
description: What this skill helps with
always: false
permissions: []
---

# Skill Title

Instructions and knowledge for the LLM.

## Guidelines
- Rule 1
- Rule 2

## Examples
User: "example input"
→ "expected response"
```

### Frontmatter Fields

| Field | Required | Description |
|-------|:--------:|-------------|
| `name` | Yes | Unique skill identifier |
| `description` | Yes | Brief description for the skill catalog |
| `always` | No | If `true`, injected into every system prompt |
| `permissions` | No | Required permissions to use this skill |

## Always vs On-Demand

- **Always skills** (`always: true`): Injected into every system prompt. Use for core behaviors like the assistant persona.
- **On-demand skills**: Listed in the "Available Skills" section. The LLM can request them when relevant.

## Creating a Custom Skill

1. Create a directory: `skills/my-skill/`
2. Create `SKILL.md` inside it
3. Write frontmatter + content
4. Deploy or restart Swarm

```markdown
---
name: chinese-holidays
description: Knowledge about Chinese public holidays and customs
---

# Chinese Holidays

## Major Holidays
- **Spring Festival (春节)**: Late January to mid-February
- **Tomb Sweeping Day (清明节)**: Early April
- **Dragon Boat Festival (端午节)**: Fifth day of the fifth lunar month
- **Mid-Autumn Festival (中秋节)**: Fifteenth day of the eighth lunar month
- **National Day (国庆节)**: October 1-7

## Guidelines
When users ask about holidays:
1. Provide exact dates for the current year
2. Mention any work schedule adjustments
3. Include traditional customs if relevant
```

## Built-in Skills

Swarm ships with these built-in skills:

| Skill | Description | Always |
|-------|-------------|:------:|
| `base-assistant` | Core persona and behavior | Yes |
| `calendar` | Calendar management | No |
| `summary` | Conversation summarization | No |
| `translator` | Multi-language translation | No |
| `code-review` | Code review assistance | No |
| `reminder` | Reminder and task tracking | No |
| `customer-support` | Customer support workflows | No |
| `data-analysis` | Data analysis and insights | No |
| `meeting-notes` | Meeting minutes generation | No |
| `feishu-docs` | Feishu document operations | No |

## Loading Skills Programmatically

```python
from pathlib import Path
from swarm.skills.loader import SkillsLoader

# Load from a directory
loader = SkillsLoader(Path("./my-skills"))

# Get always-active skills
always_names = loader.get_always_skills()
always_content = loader.load_skills_for_context(always_names)

# Get available skills summary
summary = loader.build_skills_summary()

# Inject into system prompt
system_prompt = f"""
You are a helpful assistant.

{always_content}

Available skills you can use:
{summary}
"""
```

## Best Practices

1. **One responsibility per skill**: Don't make mega-skills
2. **Include examples**: Show the LLM what good responses look like
3. **Be specific**: Vague instructions produce vague responses
4. **Keep it updated**: Skills can evolve with your needs
5. **Use permissions**: Restrict sensitive operations
