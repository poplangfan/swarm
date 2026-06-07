---
name: meeting-notes
description: Meeting notes generator — capture decisions, action items, and follow-ups
---

# Meeting Notes Skill

Generate structured, actionable meeting notes from conversations and transcripts.

## Meeting Note Template

```
# [Meeting Title]
**Date**: YYYY-MM-DD
**Time**: HH:MM - HH:MM
**Attendees**: @person1 @person2
**Facilitator**: @name
**Status**: Draft / Final

---

## Agenda
1. Topic 1
2. Topic 2
3. Topic 3

## Discussion

### Topic 1: [Name]
- Key points discussed
- Different viewpoints raised
- Supporting data referenced

### Topic 2: [Name]
...

## Decisions Made
1. **[Decision]**: [Context and rationale]
2. **[Decision]**: [Context and rationale]

## Action Items
- [ ] **Task description** — @owner (Due: YYYY-MM-DD)
- [ ] **Task description** — @owner (Due: YYYY-MM-DD)

## Open Questions
- Question 1: [Context]
- Question 2: [Context]

## Next Steps
1. [Immediate next action]
2. [Follow-up needed]

## Next Meeting
**Date/Time**: TBD / [specific time]
**Agenda**: [Preliminary topics]
```

## Guidelines

1. Capture WHO said WHAT and WHAT was DECIDED
2. Action items must have: task, owner, and deadline
3. Distinguish between decisions, suggestions, and discussion points
4. Flag unresolved items clearly
5. Send draft for review before marking as final
6. Link relevant documents, issues, or previous meeting notes

## Real-time Mode

During a meeting, capture notes progressively:
- Update the document as the meeting progresses
- Mark sections as [Draft] until confirmed
- Allow participants to correct or add points in real-time

## Post-Meeting

- Send finalized notes to all attendees
- Create calendar reminders for action item deadlines
- Archive notes in the appropriate Feishu Docs folder
