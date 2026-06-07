---
name: translator
description: Multi-language translation with context awareness
---

# Translation Skill

Translate text between languages accurately and naturally.

## Supported Languages

Primary: Chinese (Simplified), English, Japanese, Korean
Extended: French, German, Spanish, Portuguese, Russian, Arabic

## Translation Modes

### Direct Translation
Translate the given text to the target language.
Preserve formatting, code blocks, and technical terms.

### Context-Aware Translation
When translating in a conversation, maintain consistency:
- Keep names, brands, and technical terms consistent across messages
- Match the formality level of the original
- Preserve emoji and formatting where appropriate

### Document Translation
For longer documents:
- Maintain the original structure (headings, lists, tables)
- Preserve code snippets without translation
- Note any culturally-specific references that may not translate directly

## Guidelines

1. Default to the user's language unless they specify otherwise
2. For mixed-language messages, translate the non-native parts
3. Technical terms should use industry-standard translations
4. When unsure about a translation, provide alternatives
5. Idioms should be translated to equivalent expressions, not literally

## Examples

User: "Translate to English: 这个项目的截止日期是下周五"
→ "The deadline for this project is next Friday."

User: "How do you say 'quarterly review' in Chinese?"
→ "季度回顾 (jìdù huígù)"
