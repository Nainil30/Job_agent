"""Optional free notifications for NEW high-fit roles: Discord, Telegram, ntfy.sh, email (SMTP)."""

from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage

import httpx
from loguru import logger

from src.engine.models import JobRecord


def format_message(records: list[JobRecord], limit: int = 10) -> str:
    lines = [f"Job Scout: {len(records)} new high-fit role(s)"]
    for r in records[:limit]:
        lines.append(f"\n[{r.score}] {r.raw.company} - {r.raw.title}\n{r.raw.location}\n{r.raw.url}")
    if len(records) > limit:
        lines.append(f"\n...and {len(records) - limit} more in the digest.")
    return "\n".join(lines)


def configured_channels() -> list[str]:
    env = os.getenv
    channels = []
    if env("DISCORD_WEBHOOK_URL"):
        channels.append("discord")
    if env("TELEGRAM_BOT_TOKEN") and env("TELEGRAM_CHAT_ID"):
        channels.append("telegram")
    if env("NTFY_TOPIC"):
        channels.append("ntfy")
    if env("SMTP_USER") and env("SMTP_PASSWORD") and env("EMAIL_TO"):
        channels.append("email")
    return channels


def send(records: list[JobRecord]) -> list[str]:
    """Send to every configured channel. Returns channels that succeeded. Never raises."""
    if not records:
        return []
    env = os.getenv
    text = format_message(records)
    sent = []
    for channel in configured_channels():
        try:
            if channel == "discord":
                httpx.post(env("DISCORD_WEBHOOK_URL"), json={"content": text[:1900]}, timeout=20).raise_for_status()
            elif channel == "telegram":
                httpx.post(
                    f"https://api.telegram.org/bot{env('TELEGRAM_BOT_TOKEN')}/sendMessage",
                    json={"chat_id": env("TELEGRAM_CHAT_ID"), "text": text[:4000], "disable_web_page_preview": True},
                    timeout=20,
                ).raise_for_status()
            elif channel == "ntfy":
                httpx.post(
                    f"https://ntfy.sh/{env('NTFY_TOPIC')}",
                    content=text.encode("utf-8"),
                    headers={"Title": "Job Scout: new roles", "Tags": "briefcase"},
                    timeout=20,
                ).raise_for_status()
            elif channel == "email":
                msg = EmailMessage()
                msg["Subject"] = f"Job Scout: {len(records)} new high-fit role(s)"
                msg["From"] = env("SMTP_USER")
                msg["To"] = env("EMAIL_TO")
                msg.set_content(text)
                with smtplib.SMTP(env("SMTP_HOST") or "smtp.gmail.com", int(env("SMTP_PORT") or 587), timeout=30) as s:
                    s.starttls()
                    s.login(env("SMTP_USER"), env("SMTP_PASSWORD"))
                    s.send_message(msg)
            sent.append(channel)
        except Exception as exc:  # noqa: BLE001 - notifications must never fail the run
            logger.warning(f"Notification via {channel} failed: {exc}")
    if sent:
        logger.info(f"Notified {len(records)} new roles via {', '.join(sent)}")
    return sent
