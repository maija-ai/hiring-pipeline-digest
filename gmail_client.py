import os
import re
import base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
]


class GmailClient:
    def __init__(self):
        creds = Credentials(
            token=None,
            refresh_token=os.environ["GMAIL_REFRESH_TOKEN"],
            client_id=os.environ["GMAIL_CLIENT_ID"],
            client_secret=os.environ["GMAIL_CLIENT_SECRET"],
            token_uri="https://oauth2.googleapis.com/token",
            scopes=SCOPES,
        )
        creds.refresh(Request())
        self.service = build("gmail", "v1", credentials=creds)

    def resolve_label_ids(self, label_names: list[str]) -> list[str]:
        results = self.service.users().labels().list(userId="me").execute()
        all_labels = {l["name"]: l["id"] for l in results.get("labels", [])}
        label_ids = []
        for name in label_names:
            if name in all_labels:
                label_ids.append(all_labels[name])
            else:
                print(f"  Warning: Gmail label '{name}' not found, skipping.")
        return label_ids

    def build_search_query(
        self,
        sender_patterns: list[str],
        subject_keywords: list[str],
        after_date: str,
    ) -> str:
        clauses = []
        for pattern in sender_patterns:
            clauses.append(f"from:{pattern}")
        for kw in subject_keywords:
            clauses.append(f"subject:{kw}")
        inner = " OR ".join(clauses)
        return f"({inner}) after:{after_date}"

    def search_emails(
        self,
        query: str,
        label_ids: list[str] | None = None,
        max_results: int = 200,
    ) -> list[dict]:
        kwargs = {"userId": "me", "q": query, "maxResults": min(max_results, 500)}
        if label_ids:
            kwargs["labelIds"] = label_ids

        all_messages = []
        results = self.service.users().messages().list(**kwargs).execute()
        all_messages.extend(results.get("messages", []))

        while "nextPageToken" in results and len(all_messages) < max_results:
            kwargs["pageToken"] = results["nextPageToken"]
            results = self.service.users().messages().list(**kwargs).execute()
            all_messages.extend(results.get("messages", []))

        return all_messages[:max_results]

    def get_email_content(self, message_id: str) -> dict:
        msg = (
            self.service.users()
            .messages()
            .get(userId="me", id=message_id, format="full")
            .execute()
        )

        headers = msg.get("payload", {}).get("headers", [])
        header_map = {h["name"].lower(): h["value"] for h in headers}
        body_text = self._extract_body(msg.get("payload", {}))

        return {
            "id": message_id,
            "subject": header_map.get("subject", "(no subject)"),
            "sender": header_map.get("from", "(unknown)"),
            "date": header_map.get("date", ""),
            "snippet": msg.get("snippet", ""),
            "body": body_text[:5000],
        }

    def _extract_body(self, payload: dict) -> str:
        if (
            payload.get("mimeType") == "text/plain"
            and payload.get("body", {}).get("data")
        ):
            return base64.urlsafe_b64decode(payload["body"]["data"]).decode(
                "utf-8", errors="replace"
            )

        for part in payload.get("parts", []):
            result = self._extract_body(part)
            if result:
                return result

        if (
            payload.get("mimeType") == "text/html"
            and payload.get("body", {}).get("data")
        ):
            html = base64.urlsafe_b64decode(payload["body"]["data"]).decode(
                "utf-8", errors="replace"
            )
            return re.sub(r"<[^>]+>", " ", html)

        return ""

    def send_email(self, to: str, subject: str, html_body: str):
        message = MIMEMultipart("alternative")
        message["To"] = to
        message["Subject"] = subject
        message.attach(MIMEText(html_body, "html"))

        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
        sent = (
            self.service.users()
            .messages()
            .send(userId="me", body={"raw": raw})
            .execute()
        )
        return sent["id"]
