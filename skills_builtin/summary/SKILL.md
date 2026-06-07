---
name: summary
description: Conversation summarization — summarize chats, threads, and documents
---

# Summarization Skill

Generate clear, structured summaries of conversations and documents.

## Summary Types

### Chat Summary
Summarize a conversation thread into key points:
- Main topics discussed
- Decisions made
- Action items with assignees
- Open questions
- Next steps

### Meeting Summary
Structure meeting notes:
```
**Meeting**: [Title]
**Date**: [Date]
**Attendees**: [List]
**Agenda**: [Topics]
**Key Decisions**:
- Decision 1
- Decision 2
**Action Items**:
- [ ] Task 1 — @assignee (deadline)
- [ ] Task 2 — @assignee (deadline)
**Next Meeting**: [Date/Time if scheduled]
```

### Document Summary
Extract key information from long documents or articles:
- One-sentence summary (TL;DR)
- Main arguments (3-5 bullet points)
- Key data points or statistics
- Conclusions or recommendations

## Guidelines

1. Always identify the source (chat, meeting, document)
2. Prioritize actionable information over background context
3. Use the @mention format for Feishu users in action items
4. Keep summaries under 500 words when possible
5. Highlight decisions clearly — these are the most important output

## Anti-patterns

- Don't just list every message chronologically — synthesize
- Don't lose important nuance in pursuit of brevity
- Don't include irrelevant small talk
