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
{f"The roles currently being hired for are: {roles_str}." if roles_str else "Discover all roles and companies from the email content."}

Return a JSON object (no markdown fencing, just raw JSON) with this structure:

{{
  "overall_summary": "2-3 sentence executive summary of hiring activity",
  "roles": [
    {{
      "role": "Role Name",
      "company": "Company Name",
      "emails": [
        {{
          "subject": "Email subject line",
          "date": "Date",
          "summary": "1-2 sentence summary of what this email is about"
        }}
      ],
      "todos": [
        {{
          "priority": "high|medium|low",
          "description": "What needs to be done",
          "deadline": "When it needs to happen or null"
        }}
      ]
    }}
  ],
  "general_todos": [
    {{
      "priority": "high|medium|low",
      "description": "Action items not tied to a specific role",
      "deadline": "When it needs to happen or null"
    }}
  ]
}}

Rules:
- Group emails by role and company. Extract the company name from email threads (e.g., "Mark / Soldera intro" means the company is Soldera).
- If a roles list is provided, include all of them. Otherwise, discover roles and companies from the email content. Only include roles that appear in the emails.
- For each role, list the relevant emails with a brief summary of each.
- For each role, list actionable to-dos based on the emails.
- CRITICAL: Before adding a to-do, check whether it has ALREADY BEEN DONE. Look at the full email thread context:
  - If someone requested scheduling and a confirmation/reply already exists, do NOT add "schedule interview" as a to-do.
  - If a follow-up was requested and a response already exists in the thread, do NOT add "respond to X" as a to-do.
  - If an intro was made and both parties have already connected, do NOT add "make intro" as a to-do.
  - Only include to-dos for things that genuinely still need action as of today.
- Mark to-dos "high" priority if they involve: interviews today/tomorrow, expiring offers, overdue responses with no reply.
- general_todos is for action items not tied to a specific role (e.g., recruiter meetings, platform admin tasks).
- If an email is not related to hiring, skip it entirely.
- Do not fabricate information. If data is ambiguous, say so."""

    def _user_prompt(self, email_text: str) -> str:
        return f"""Here are the hiring-related emails from the last 48 hours. \
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
                "roles": [],
                "general_todos": [],
                "_raw_response": text,
            }
