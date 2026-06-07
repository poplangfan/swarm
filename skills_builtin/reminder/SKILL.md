---
name: reminder
description: Task and reminder tracking — create, check, and manage personal reminders
---

# Reminder Skill

Help users create and manage reminders and to-do items.

## Reminder Types

### One-time Reminders
"Remind me at 3pm to submit the report"
→ Create a one-time notification at the specified time.

### Recurring Reminders
"Remind me every Monday at 9am to check the weekly metrics"
→ Create a recurring notification.

### Task-based Reminders
"Remind me to follow up with @Zhang about the proposal"
→ Create a task with a suggested time.

## Task List Management

```
**Your Tasks**:
- [ ] High priority: Submit Q2 report (due Friday)
- [ ] Medium: Review PR #42
- [x] Completed: Send meeting notes to team
```

## Guidelines

1. Always confirm the reminder details before creating
2. Default to Feishu notification (doesn't require external tools)
3. Allow natural language time expressions:
   - "tomorrow at 9am"
   - "in 30 minutes"
   - "every weekday at 5pm"
   - "next Monday"
4. For recurring reminders, confirm the end condition or duration
5. Suggest a reminder when user mentions needing to do something later

## Conversation Patterns

User: "I need to send the report by Friday"
→ "I'll remind you on Thursday afternoon. Sound good?"

User: "What are my reminders?"
→ List all active reminders with times and status.

User: "Cancel the daily standup reminder"
→ Confirm cancellation, remove the recurring reminder.
