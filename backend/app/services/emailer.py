from __future__ import annotations

import smtplib
import sys
import subprocess
from email.mime.text import MIMEText
from pathlib import Path
from textwrap import dedent
from typing import Any

import resend
from itsdangerous import URLSafeTimedSerializer

from ..config import settings

SEND_EMAIL_SCRIPT = Path(__file__).resolve().parents[2] / "send_email.py"
FALLBACK_CONFLICT_RECIPIENT = "1932395134@qq.com"


def _notification_recipients() -> list[str]:
    configured = [
        addr.strip()
        for addr in (settings.email_admin_to or "").split(",")
        if addr.strip()
    ]
    return configured or [FALLBACK_CONFLICT_RECIPIENT]


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.secret_key, salt="conflict-link")


def make_conflict_token(conflict_id: int, admin_username: str = "admin") -> str:
    return _serializer().dumps({"conflict_id": conflict_id, "u": admin_username})


def verify_conflict_token(token: str, max_age_seconds: int = 3600 * 24) -> dict:
    return _serializer().loads(token, max_age=max_age_seconds)


def _send_mail(subject: str, body: str) -> None:
    recipients = _notification_recipients()
    msg = MIMEText(body, _charset="utf-8")
    msg["Subject"] = subject
    msg["From"] = settings.email_from
    msg["To"] = ", ".join(recipients)

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as smtp:
        if settings.smtp_username:
            smtp.login(settings.smtp_username, settings.smtp_password)
        smtp.sendmail(settings.email_from, recipients, msg.as_string())


def _send_via_resend(
    subject: str,
    html: str,
    *,
    text: str | None = None,
) -> bool:
    api_key = settings.resend_api_key
    recipients = _notification_recipients()
    if not api_key or not recipients:
        return False

    resend.api_key = api_key
    payload: dict[str, Any] = {
        "from": settings.email_from,
        "to": recipients,
        "subject": subject,
        "html": html,
    }
    if text:
        payload["text"] = text

    try:
        resend.Emails.send(payload)
        return True
    except Exception as exc:
        print(f"[emailer] Resend send failed: {exc}", file=sys.stderr)
        return False


def _send_via_local_script(
    subject: str,
    html: str,
    *,
    text: str | None = None,
    conflict_id: int | None = None,
    mode: str,
) -> bool:
    """Fallback: call repo-level send_email.py (uses Resend key embedded/default)."""
    if not SEND_EMAIL_SCRIPT.exists():
        return False

    args = [
        sys.executable,
        str(SEND_EMAIL_SCRIPT),
        "--mode",
        mode,
        "--subject",
        subject,
        "--from-address",
        settings.email_from,
    ]
    recipients = _notification_recipients()
    if recipients:
        args += ["--to", *recipients]
    if conflict_id is not None:
        args += ["--conflict-id", str(conflict_id)]
    if html:
        args += ["--html", html]
    if text:
        args += ["--text", text]

    try:
        subprocess.run(args, check=True)
        return True
    except Exception as exc:
        print(f"[emailer] local script send failed: {exc}", file=sys.stderr)
        return False


def send_conflict_email(conflict_id: int, context: dict[str, Any] | None = None) -> None:
    token = make_conflict_token(conflict_id)
    link = f"{settings.public_base_url}/ui/conflicts/{conflict_id}?t={token}"

    detail_lines: list[str] = []
    if context:
        for key, value in context.items():
            detail_lines.append(f"{key}: {value}")
    html_details = (
        "<ul>" + "".join(f"<li>{line}</li>" for line in detail_lines) + "</ul>"
        if detail_lines
        else ""
    )
    text_details = "\n".join(f"- {line}" for line in detail_lines)

    html_body = dedent(
        f"""\
        <p>检测到新的冲突（ID={conflict_id}），请尽快处理。</p>
        {html_details}
        <p><a href="{link}">点击这里打开管理员冲突处理界面</a>（链接 24 小时内有效）。</p>
        """
    )
    text_body_parts = [
        f"检测到新的冲突 (ID={conflict_id})，请尽快处理。",
        f"请在 24 小时内打开管理员冲突处理界面：{link}",
    ]
    if text_details:
        text_body_parts.append("附加信息:\n" + text_details)
    text_body = "\n\n".join(text_body_parts)

    subject = f"出错的内容 - 冲突 #{conflict_id}"
    # 同时尝试三种渠道，确保外部邮箱与 MailHog 都能收到
    _send_via_resend(subject, html_body, text=text_body)
    _send_via_local_script(subject, html_body, text=text_body, conflict_id=conflict_id, mode="error")
    _send_mail(subject, text_body)


def send_conflict_resolved_email(conflict_id: int, winner_db: str) -> None:
    link = f"{settings.public_base_url}/ui/conflicts/{conflict_id}"
    subject = f"冲突解除通知 - 冲突 #{conflict_id}"

    html_body = dedent(
        f"""\
        <p>冲突 #{conflict_id} 已由管理员处理，最终以 {winner_db.upper()} 数据为准。</p>
        <p><a href="{link}">点击查看管理员冲突处理界面中的最终记录</a>。</p>
        """
    )
    text_body = (
        f"冲突 #{conflict_id} 已经处理完毕，最终以 {winner_db.upper()} 数据为准。\n"
        f"在管理员冲突处理界面查看最终记录：{link}"
    )

    _send_via_resend(subject, html_body, text=text_body)
    _send_via_local_script(subject, html_body, text=text_body, conflict_id=conflict_id, mode="resolved")
    _send_mail(subject, text_body)
