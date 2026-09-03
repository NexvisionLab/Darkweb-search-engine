"""Weekly digest email - new ransomware victims and newly-flagged
Suspicious/Dangerous sites from the last 7 days, sent to everyone with
an active subscription. Meant to run on a weekly systemd timer (see
ops/systemd/darkweb-digest.timer, not yet installed).

SMTP credentials are a real external dependency this platform doesn't
have yet - SMTP_HOST/SMTP_PORT/SMTP_USER/SMTP_PASSWORD/DIGEST_FROM_EMAIL
in .env are all empty placeholders. Rather than fail loudly (this runs
unattended on a timer) or fake success, an unconfigured SMTP_HOST makes
this a dry run: the digest is generated and printed, nothing is sent.
Wire up a real transactional-email provider's SMTP credentials (or any
plain SMTP relay) to make it live - the sending code itself needs no
changes, same pattern as DEEPINFRA_API_KEY elsewhere in this project."""
import os
import smtplib
import sys
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText

sys.path.insert(0, ".")
from darkweb_crawler import db

RATING_LABELS = {
    "illicit-marketplace": "Suspicious",
    "exit-scam-suspect": "Suspicious",
    "fraud-risk": "Dangerous",
    "confirmed-leak": "Dangerous",
    "malware-risk": "Dangerous",
    "phishing-clone-suspect": "Dangerous",
}

SMTP_HOST = os.environ.get("SMTP_HOST", "").strip()
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587") or "587")
SMTP_USER = os.environ.get("SMTP_USER", "").strip()
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "").strip()
DIGEST_FROM_EMAIL = os.environ.get("DIGEST_FROM_EMAIL", "").strip()

SITE_URL = "https://darknyx.com"


def build_digest_text(victims, flagged, unsubscribe_token):
    lines = ["DarkNyx weekly digest", ""]

    if victims:
        lines.append(f"New ransomware victims this week ({len(victims)}):")
        for v in victims[:25]:
            lines.append(f"  - {v['group_name']}: {v['victim_name']}")
        if len(victims) > 25:
            lines.append(f"  ...and {len(victims) - 25} more")
        lines.append("")
    else:
        lines.append("No new ransomware victims this week.")
        lines.append("")

    if flagged:
        lines.append(f"Newly flagged sites this week ({len(flagged)}):")
        for f in flagged[:25]:
            label = RATING_LABELS.get(f["safety_rating"], f["safety_rating"])
            lines.append(f"  - {f['host']} - {label}")
        if len(flagged) > 25:
            lines.append(f"  ...and {len(flagged) - 25} more")
        lines.append("")
    else:
        lines.append("No newly flagged sites this week.")
        lines.append("")

    lines.append(f"See more at {SITE_URL}")
    lines.append(f"Unsubscribe: {SITE_URL}/api/digest/unsubscribe/{unsubscribe_token}")
    return "\n".join(lines)


def send_email(to_email, body_text):
    msg = MIMEText(body_text)
    msg["Subject"] = "DarkNyx weekly digest"
    msg["From"] = DIGEST_FROM_EMAIL
    msg["To"] = to_email

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        if SMTP_USER:
            server.login(SMTP_USER, SMTP_PASSWORD)
        server.sendmail(DIGEST_FROM_EMAIL, [to_email], msg.as_string())


def main():
    conn = db.get_connection()
    since = datetime.now(timezone.utc) - timedelta(days=7)
    victims = db.get_new_ransomware_victims_since(conn, since)
    flagged = db.get_newly_flagged_domains_since(conn, since)
    subscribers = db.get_active_digest_subscriptions(conn)
    conn.close()

    dry_run = not SMTP_HOST
    if dry_run:
        print("SMTP_HOST not configured - dry run, nothing will be sent.")

    sent = 0
    for sub in subscribers:
        body = build_digest_text(victims, flagged, sub["unsubscribe_token"])
        if dry_run:
            print(f"--- would send to {sub['email']} ---")
            print(body)
            print("---")
            continue
        try:
            send_email(sub["email"], body)
            sent += 1
        except Exception as e:
            print(f"Failed to send to {sub['email']}: {e}")

    if dry_run:
        print(f"Dry run complete: {len(subscribers)} subscriber(s), {len(victims)} new victims, {len(flagged)} newly flagged")
    else:
        print(f"Sent {sent}/{len(subscribers)} digest emails")


if __name__ == "__main__":
    main()
