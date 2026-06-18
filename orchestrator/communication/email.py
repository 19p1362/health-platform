"""
Healthcare Orchestra — Email Service.

Sends email notifications via SMTP. Falls back gracefully when SMTP
is not configured.
"""

from __future__ import annotations

import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from config import config

logger = logging.getLogger("healthcare_orchestra.email")


def send_email(
    to: str,
    subject: str,
    body: str,
    cc: str | None = None,
) -> bool:
    """Send an email notification.

    Args:
        to: Recipient email address.
        subject: Email subject line.
        body: Email body text.
        cc: Optional CC address.

    Returns:
        True if the email was sent successfully (or queued), False otherwise.
    """
    if not config.SMTP_HOST or config.SMTP_HOST == "localhost":
        # Check if SMTP is actually running — if not, log and degrade gracefully
        try:
            with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=5) as smtp:
                if config.SMTP_USER and config.SMTP_PASSWORD:
                    smtp.starttls()
                    smtp.login(config.SMTP_USER, config.SMTP_PASSWORD)
                msg = MIMEMultipart("alternative")
                msg["From"] = config.SMTP_FROM
                msg["To"] = to
                msg["Subject"] = subject
                if cc:
                    msg["Cc"] = cc
                msg.attach(MIMEText(body, "plain"))
                recipients = [to]
                if cc:
                    recipients.append(cc)
                smtp.sendmail(config.SMTP_FROM, recipients, msg.as_string())
                logger.info("Email sent to %s: %s", to, subject)
                return True
        except (smtplib.SMTPException, ConnectionRefusedError, OSError) as exc:
            logger.warning(
                "Email sending failed (SMTP unavailable): %s — "
                "logging message instead", exc,
            )
            logger.info("EMAIL [to=%s, subject=%s]: %s", to, subject, body[:200])
            return False
    else:
        # Configured SMTP
        try:
            with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=10) as smtp:
                smtp.starttls()
                if config.SMTP_USER and config.SMTP_PASSWORD:
                    smtp.login(config.SMTP_USER, config.SMTP_PASSWORD)
                msg = MIMEMultipart("alternative")
                msg["From"] = config.SMTP_FROM
                msg["To"] = to
                msg["Subject"] = subject
                if cc:
                    msg["Cc"] = cc
                msg.attach(MIMEText(body, "plain"))
                recipients = [to]
                if cc:
                    recipients.append(cc)
                smtp.sendmail(config.SMTP_FROM, recipients, msg.as_string())
                logger.info("Email sent to %s: %s", to, subject)
                return True
        except Exception as exc:
            logger.error("Email sending failed: %s", exc)
            return False
