"""Cron management tool — create, list, delete scheduled tasks via LLM."""

from __future__ import annotations

from agent.context import RequestContext
from tools.base import ToolBase, tool_result


class CronTool(ToolBase):
    name = "cron_manage"
    description = "Create, list, or delete scheduled tasks and reminders"
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["list", "create_reminder", "delete"],
                "description": "Cron action to perform",
            },
            "job_id": {
                "type": "string",
                "description": "Job ID (required for delete)",
            },
            "description": {
                "type": "string",
                "description": "Task description (for create)",
            },
            "minutes_from_now": {
                "type": "integer",
                "description": "Minutes from now to run (for create_reminder)",
            },
        },
        "required": ["action"],
    }

    def __init__(self, scheduler=None):
        self._scheduler = scheduler
        self._reminders: dict[str, dict] = {}
        self._counter = 0

    async def execute(self, args: dict, ctx: RequestContext) -> str:
        action = args.get("action", "list")

        if action == "list":
            if self._scheduler:
                jobs = self._scheduler.list_jobs()
                if not jobs:
                    return tool_result("No scheduled tasks")
                lines = [f"- {j['id']}: {j.get('type', 'unknown')}" for j in jobs]
                return tool_result(f"Scheduled tasks ({len(jobs)}):", tasks="\n".join(lines))
            else:
                reminders = list(self._reminders.values())
                if not reminders:
                    return tool_result("No reminders scheduled")
                lines = [f"- {r['id']}: {r['description']}" for r in reminders]
                return tool_result(f"Reminders ({len(reminders)}):", tasks="\n".join(lines))

        elif action == "create_reminder":
            desc = args.get("description", "Reminder")
            minutes = max(1, int(args.get("minutes_from_now", 5)))
            self._counter += 1
            job_id = f"reminder_{self._counter}"
            self._reminders[job_id] = {
                "id": job_id,
                "description": desc,
                "minutes": minutes,
                "chat_id": ctx.chat_id,
            }

            # Schedule via CronScheduler if available
            if self._scheduler:
                self._scheduler.add_interval_job(
                    job_id=job_id,
                    func=lambda: None,  # Placeholder — real impl would send message
                    minutes=minutes,
                )

            return tool_result(f"Reminder created: '{desc}' in {minutes} minutes", job_id=job_id)

        elif action == "delete":
            job_id = args.get("job_id", "")
            if not job_id:
                return tool_result("Missing job_id for delete")
            if self._scheduler:
                if self._scheduler.remove_job(job_id):
                    return tool_result(f"Deleted: {job_id}")
            if job_id in self._reminders:
                del self._reminders[job_id]
                return tool_result(f"Deleted reminder: {job_id}")
            return tool_result(f"Job not found: {job_id}")

        return tool_result(f"Unknown cron action: {action}")
