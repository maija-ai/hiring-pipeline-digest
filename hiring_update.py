#!/usr/bin/env python3
"""Daily Hiring Pipeline Digest Generator.

Reads hiring-related emails from Gmail, summarizes them with Claude,
and sends a formatted HTML digest email.
"""

import os
import sys
import datetime
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader

from gmail_client import GmailClient
from claude_summarizer import HiringSummarizer


def load_config(config_path: str = "config.yaml") -> dict:
    with open(config_path) as f:
        return yaml.safe_load(f)


def compute_lookback_date(hours: int) -> str:
    dt = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=hours)
    return dt.strftime("%Y/%m/%d")


def main():
    print("=== Hiring Pipeline Digest ===")
    print(f"Run time: {datetime.datetime.now(datetime.timezone.utc).isoformat()}")

    config = load_config()
    recipient = os.environ.get("RECIPIENT_EMAIL")
    if not recipient:
        print("ERROR: RECIPIENT_EMAIL environment variable not set.")
        sys.exit(1)

    # Connect to Gmail
    print("Connecting to Gmail API...")
    try:
        gmail = GmailClient()
    except Exception as e:
        print(f"ERROR: Failed to connect to Gmail API: {e}")
        sys.exit(1)

    # Build search parameters
    gmail_config = config.get("gmail", {})
    lookback_hours = gmail_config.get("lookback_hours", 48)
    max_emails = gmail_config.get("max_emails", 200)
    after_date = compute_lookback_date(lookback_hours)

    query = gmail.build_search_query(
        sender_patterns=gmail_config.get("sender_patterns", []),
        subject_keywords=gmail_config.get("subject_keywords", []),
        after_date=after_date,
    )
    print(f"Gmail search query: {query}")

    # Search by query patterns
    all_message_ids = set()

    print("Searching by sender/subject patterns...")
    results_query = gmail.search_emails(query, max_results=max_emails)
    for msg in results_query:
        all_message_ids.add(msg["id"])
    print(f"  Found {len(results_query)} emails by query.")

    # Search by labels
    label_names = gmail_config.get("labels", [])
    if label_names:
        label_ids = gmail.resolve_label_ids(label_names)
        if label_ids:
            print(f"Searching by labels: {label_names}...")
            results_labels = gmail.search_emails(
                f"after:{after_date}", label_ids=label_ids, max_results=max_emails
            )
            for msg in results_labels:
                all_message_ids.add(msg["id"])
            print(f"  Found {len(results_labels)} emails by labels.")

    print(f"Total unique emails: {len(all_message_ids)}")

    roles = config.get("roles", [])

    if not all_message_ids:
        print("No hiring emails found. Sending minimal digest.")
        summary = {
            "overall_summary": "No hiring-related emails were found in the last 48 hours.",
            "pipeline_summary": [
                {
                    "role": r,
                    "sourced": 0,
                    "contacted": 0,
                    "interviewing": 0,
                    "offered": 0,
                    "notes": "No recent activity",
                }
                for r in roles
            ],
            "action_items": [],
            "recent_activity": [],
        }
    else:
        # Fetch full email content
        print("Fetching email content...")
        emails = []
        for msg_id in all_message_ids:
            try:
                emails.append(gmail.get_email_content(msg_id))
            except Exception as e:
                print(f"  Warning: Failed to fetch email {msg_id}: {e}")

        print(f"Successfully fetched {len(emails)} emails.")
        emails.sort(key=lambda e: e.get("date", ""), reverse=True)

        # Summarize with Claude
        print("Sending to Claude for summarization...")
        claude_config = config.get("claude", {})
        summarizer = HiringSummarizer(
            model=claude_config.get("model", "claude-sonnet-4-20250514"),
            max_tokens=claude_config.get("max_tokens", 4096),
        )

        try:
            summary = summarizer.summarize(
                emails=emails,
                roles=roles,
                today_str=datetime.date.today().isoformat(),
            )
        except Exception as e:
            print(f"ERROR: Claude API call failed: {e}")
            summary = {
                "overall_summary": f"Claude summarization failed ({e}). Raw email subjects listed below.",
                "pipeline_summary": [],
                "action_items": [],
                "recent_activity": [
                    {
                        "timestamp": em["date"],
                        "description": f"{em['subject']} (from {em['sender']})",
                        "source": "Gmail",
                    }
                    for em in emails[:20]
                ],
            }

    # Render HTML email
    print("Rendering email template...")
    env = Environment(loader=FileSystemLoader(Path(__file__).parent / "templates"))
    template = env.get_template("digest_email.html")

    today_formatted = datetime.date.today().strftime("%A, %B %d, %Y")
    email_config = config.get("email", {})
    subject = f"{email_config.get('subject_prefix', '[Hiring Digest]')} {today_formatted}"

    html_body = template.render(
        summary=summary,
        today_formatted=today_formatted,
        email_count=len(all_message_ids),
        lookback_hours=lookback_hours,
    )

    # Send digest
    print(f"Sending digest to {recipient}...")
    try:
        sent_id = gmail.send_email(to=recipient, subject=subject, html_body=html_body)
        print(f"Digest sent successfully. Gmail message ID: {sent_id}")
    except Exception as e:
        print(f"ERROR: Failed to send digest email: {e}")
        sys.exit(1)

    print("=== Done ===")


if __name__ == "__main__":
    main()
