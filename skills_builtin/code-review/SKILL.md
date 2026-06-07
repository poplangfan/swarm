---
name: code-review
description: Code review assistant — analyze code, suggest improvements, find bugs
---

# Code Review Skill

Help developers review code for quality, correctness, and best practices.

## Review Dimensions

### Correctness
- Does the code do what it claims to do?
- Are edge cases handled?
- Are there potential null/None reference issues?
- Is error handling adequate?

### Performance
- Are there obvious O(n²) loops that could be O(n)?
- Are database queries properly indexed?
- Is memory usage reasonable?
- Are there unnecessary allocations?

### Security
- Is user input validated and sanitized?
- Are credentials or secrets exposed?
- Are there SQL injection or XSS vulnerabilities?
- Is authentication/authorization properly checked?

### Style & Maintainability
- Is the code readable and well-named?
- Are functions focused and small?
- Is there adequate test coverage?
- Are comments explaining WHY, not WHAT?

## Review Format

```
**File**: path/to/file.py
**Overall**: [Brief assessment]

**Issues Found**:
1. **[Severity: High/Medium/Low]** [Description]
   - Location: line X
   - Suggestion: [How to fix]

**Suggestions**:
- [Optional improvements that aren't bugs]

**Summary**: [1-2 sentence overall assessment]
```

## Guidelines

1. Be constructive, not critical — focus on improvement
2. Prioritize bugs and security issues over style preferences
3. Provide concrete fix examples, not abstract advice
4. Acknowledge what's done well
5. Don't review generated or auto-formatted code unless asked
