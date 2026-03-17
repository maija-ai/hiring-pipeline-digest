import os
import json

from anthropic import Anthropic


class HiringSummarizer:
    def __init__(self, model: str = "claude-sonnet-4-20250514", max_tokens: int = 4096):
        self.client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        self.model = model
        self.max_tokens = max_tokens

    def summarize(self, emails: list[dict], roles: list[str], today_str: str) -> dict:
        email_text = self._format_emails(emails)
        system = self._system_prompt(roles, today_str)
        user = self._user_prompt(email_text)

        response = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return self._parse_response(response.content[0].text)

    def _format_emails(self, emails: list[dict]) -> str:
        MAX_TOTAL_CHARS = 150_000
        parts = []
        total = 0
        for i, email in enumerate(emails, 1):
            content = email["body"] if email["body"] else email["snippet"]
            if total + len(content) > MAX_TOTAL_CHARS:
                content = email["snippet"]
            if total + len(content) > MAX_TOTAL_CHARS:
                parts.append(
                    f"\n[... {len(emails) - i} more emails truncated ...]"
                )
                break
            block = (
                f"--- Email {i} ---\n"
                f"From: {email['sender']}\n"
                f"Subject: {email['subject']}\n"
                f"Date: {email['date']}\n"
                f"Content:\n{content}\n"
            )
            parts.append(block)
            total += len(block)
        return "\n".join(parts)

    def _system_prompt(self, roles: list[str], today_str: str) -> str:
        roles_str = ", ".join(roles)
        return f"""You are a hiring operations analyst. Your job is to read through \
hiring-related emails and produce a structured daily briefing for a hiring manager.

Today's date is {today_str}.
The roles currently being hired for are: {roles_str}.

Return a JSON object (no markdown fencing, just raw JSON) with this structure:

{{
  "overall_summary": "2-3 sentence executive summary of hiring activity",
  "pipeline_summary": [
    {{
      "role": "Role Name",
      "company": "Company Name",
      "sourced": 0,
      "contacted": 0,
      "interviewing": 0,
      "offered": 0,
      "notes": "Brief notes about this role's pipeline"
    }}
  ],
  "action_items": [
    {{
      "priority": "high|medium|low",
      "description": "What needs to be done",
      "deadline": "When it needs to happen"
    }}
  ],
  "recent_activity": [
    {{
      "timestamp": "Approximate date/time",
      "description": "What happened",
      "source": "Which email or platform this came from"
    }}
  ]
}}

Rules:
- Include ALL roles from the active roles list, even if no activity. Set counts to 0 and note "No recent activity".
- Extract the company name from email threads (e.g., "Mark / Soldera intro" means the company is Soldera). Always include the company name for each role.
- For pipeline counts, infer the stage from email context (e.g., "scheduled interview" = interviewing stage).
- Action items should be specific and actionable. Flag anything needing a reply, decision, or with a deadline.
- Mark action items "high" priority if they involve: interviews today/tomorrow, expiring offers, overdue responses.
- recent_activity should be in reverse chronological order (newest first).
- If you cannot determine exact counts, provide your best estimate and note the uncertainty.
- If an email is not related to hiring, skip it entirely.
- Do not fabricate information. If data is ambiguous, say so in the notes."""

    def _user_prompt(self, email_text: str) -> str:
        return f"""Here are the hiring-related emails from the last 24-48 hours. \
Analyze them and produce the structured JSON briefing.

{email_text}

Return only the JSON object, no other text."""

    def _parse_response(self, text: str) -> dict:
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {
                "overall_summary": "Failed to parse structured response. Raw output included below.",
                "pipeline_summary": [],
                "action_items": [],
                "recent_activity": [],
                "_raw_response": text,
            }
