"""Natural language → cron expression parser (LLM-assisted + rule-based fallback)."""

from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timedelta


class CronParser:
    """Parse natural language time expressions into cron expressions.

    Supports both LLM-assisted parsing (when a provider is available) and
    rule-based fallback for common patterns.

    Examples:
    - "every day at 9am" → "0 9 * * *"
    - "every Monday at 2pm" → "0 14 * * 1"
    - "every 30 minutes" → "*/30 * * * *"
    - "tomorrow at 3pm" → (calculated date + "0 15 D M *")
    """

    # Common time patterns → (minute, hour, day_of_month, month, day_of_week)
    PATTERNS: list[tuple[str, str]] = [
        # Every day at specific time
        (r"every\s+day\s+at\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", r"0 \1 * * *"),
        # Every weekday
        (r"every\s+weekday\s+at\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", r"0 \1 * * 1-5"),
        # Every Monday/Tuesday/etc
        (r"every\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+at\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", None),
        # Every N minutes/hours
        (r"every\s+(\d+)\s+minutes?", r"*/\1 * * * *"),
        (r"every\s+(\d+)\s+hours?", r"0 */\1 * * *"),
        # Daily at time
        (r"daily\s+at\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", r"0 \1 * * *"),
        # Weekly
        (r"weekly\s+at\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", r"0 \1 * * 0"),
        # Monthly
        (r"monthly\s+on\s+day\s+(\d{1,2})\s+at\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", r"0 \2 \1 * *"),
    ]

    DAY_NAMES = {
        "monday": 1, "tuesday": 2, "wednesday": 3,
        "thursday": 4, "friday": 5, "saturday": 6, "sunday": 0,
        "mon": 1, "tue": 2, "wed": 3, "thu": 4, "fri": 5, "sat": 6, "sun": 0,
    }

    LLM_TIMEOUT = 10.0  # seconds

    async def parse(self, text: str, provider=None) -> dict:
        """Parse a natural language time expression into cron details.

        Returns: {
            "cron": "0 9 * * *",
            "description": "Every day at 9:00 AM",
            "next_run": "2026-06-08T09:00:00",
            "confidence": 0.9,
        }
        """
        text = text.lower().strip()

        # Try LLM-assisted parsing
        if provider:
            result = await self._llm_parse(text, provider)
            if result and result.get("confidence", 0) > 0.7:
                return result

        # Rule-based fallback
        return self._rule_parse(text)

    async def _llm_parse(self, text: str, provider) -> dict | None:
        """Use LLM to parse the time expression."""
        try:
            prompt = f"""Convert this time expression to a cron expression and structured output:

Time expression: "{text}"

Respond with ONLY a JSON object:
{{
    "cron": "minute hour day_of_month month day_of_week",
    "description": "human readable description",
    "confidence": 0.0-1.0
}}

Examples:
"every day at 9am" → {{"cron": "0 9 * * *", "description": "Every day at 9:00 AM", "confidence": 1.0}}
"every Monday at 2pm" → {{"cron": "0 14 * * 1", "description": "Every Monday at 2:00 PM", "confidence": 1.0}}
"every 30 minutes" → {{"cron": "*/30 * * * *", "description": "Every 30 minutes", "confidence": 1.0}}"""

            response = await asyncio.wait_for(
                provider.chat(
                    messages=[{"role": "user", "content": prompt}],
                ),
                timeout=self.LLM_TIMEOUT,
            )
            if response and response.content:
                try:
                    return json.loads(response.content)
                except json.JSONDecodeError:
                    pass
            return None
        except asyncio.TimeoutError:
            return None
        except Exception:
            return None

    def _rule_parse(self, text: str) -> dict:
        """Rule-based natural language → cron parsing."""
        # Check each pattern
        for pattern, template in self.PATTERNS:
            match = re.match(pattern, text, re.IGNORECASE)
            if match and template:
                cron = self._apply_template(template, match)
                return {
                    "cron": cron,
                    "description": self._describe_cron(cron),
                    "confidence": 0.8,
                }
            elif match:
                return self._handle_day_pattern(match)

        # Default: try to extract time
        time_match = re.search(r"at\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", text)
        if time_match:
            hour = int(time_match.group(1))
            minute = int(time_match.group(2)) if time_match.group(2) else 0
            ampm = time_match.group(3)
            if ampm == "pm" and hour < 12:
                hour += 12
            if ampm == "am" and hour == 12:
                hour = 0
            cron = f"{minute} {hour} * * *"
            return {"cron": cron, "description": self._describe_cron(cron),
                    "confidence": 0.5}

        return {"cron": "0 9 * * *", "description": "Every day at 9:00 AM (default)",
                "confidence": 0.1, "note": "Could not parse time expression, using default"}

    def _apply_template(self, template: str, match: re.Match) -> str:
        """Apply a regex match to a cron template, handling AM/PM conversion."""
        groups = match.groups()
        # Find am/pm group position and hour group position
        ampm = None
        hour_idx = None
        for i, g in enumerate(groups):
            if g and isinstance(g, str) and g.lower() in ("am", "pm"):
                ampm = g.lower()
            elif g and g.isdigit() and hour_idx is None:
                # First numeric group is typically the hour
                hour_idx = i

        # Apply template substitution
        cron = re.sub(r'\\(\d+)', lambda m: str(groups[int(m.group(1)) - 1] or "0"), template)

        # Adjust hour for PM
        if ampm == "pm" and hour_idx is not None:
            hour_val = int(groups[hour_idx])
            if hour_val < 12:
                hour_val += 12
            parts = cron.strip().split()
            if len(parts) == 5:
                parts[1] = str(hour_val)
                cron = " ".join(parts)

        return cron

    def _handle_day_pattern(self, match: re.Match) -> dict:
        """Handle day-of-week patterns."""
        groups = match.groups()
        day_name = groups[0].lower()
        hour_str = groups[1]
        minute_str = groups[2] if groups[2] else "0"
        ampm = groups[3] if len(groups) > 3 else None

        hour = int(hour_str)
        minute = int(minute_str) if minute_str else 0

        if ampm == "pm" and hour < 12:
            hour += 12
        if ampm == "am" and hour == 12:
            hour = 0

        day_num = self.DAY_NAMES.get(day_name, 0)
        cron = f"{minute} {hour} * * {day_num}"
        return {"cron": cron, "description": self._describe_cron(cron),
                "confidence": 0.9}

    def _describe_cron(self, cron: str) -> str:
        """Generate a human-readable description of a cron expression."""
        parts = cron.strip().split()
        if len(parts) != 5:
            return f"Cron: {cron}"

        minute, hour, dom, month, dow = parts

        # Every N minutes
        if minute.startswith("*/"):
            n = minute[2:]
            return f"Every {n} minutes"

        # Every N hours
        if hour.startswith("*/"):
            n = hour[2:]
            return f"Every {n} hours"

        # Daily at specific time
        if dom == "*" and month == "*" and dow == "*":
            return f"Every day at {hour}:{minute.zfill(2)}"

        # Weekday
        if dom == "*" and month == "*" and dow == "1-5":
            return f"Every weekday at {hour}:{minute.zfill(2)}"

        # Specific day of week
        if dom == "*" and month == "*" and dow.isdigit():
            day_names = {v: k for k, v in self.DAY_NAMES.items()}
            day = day_names.get(int(dow), dow)
            return f"Every {day} at {hour}:{minute.zfill(2)}"

        # Monthly on specific day
        if dom.isdigit() and month == "*" and dow == "*":
            return f"Monthly on day {dom} at {hour}:{minute.zfill(2)}"

        return f"Cron: {cron}"

    def calculate_next_run(self, cron: str) -> str | None:
        """Calculate the next run time for a cron expression.

        Returns ISO format datetime string.
        """
        parts = cron.strip().split()
        if len(parts) != 5:
            return None

        try:
            minute, hour, dom, month, dow = parts
            now = datetime.now()
            candidate = now.replace(second=0, microsecond=0)

            # Simple case: daily at time
            if dom == "*" and month == "*" and dow == "*" and not minute.startswith("*") and not hour.startswith("*"):
                candidate = candidate.replace(hour=int(hour), minute=int(minute))
                if candidate <= now:
                    candidate += timedelta(days=1)
                return candidate.isoformat()

            # Every N minutes
            if minute.startswith("*/"):
                n = int(minute[2:])
                next_minute = ((now.minute // n) + 1) * n
                if next_minute >= 60:
                    candidate = candidate.replace(minute=0) + timedelta(hours=1)
                    candidate = candidate.replace(minute=0)
                else:
                    candidate = candidate.replace(minute=next_minute)
                return candidate.isoformat()

            # Default: next hour at minute 0
            candidate = candidate.replace(minute=0) + timedelta(hours=1)
            return candidate.isoformat()

        except (ValueError, IndexError):
            return None
