from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from typing import List

import resend

# Prefer environment variables but keep the known working default for local use.
DEFAULT_API_KEY = os.getenv("RESEND_API_KEY", "re_8Th4yY1r_2TNJt2ktWhwsEVra2h55t1W5")
DEFAULT_SENDER = os.getenv("EMAIL_FROM", "error@burgerbin.top")
DEFAULT_RECIPIENTS = [
    addr.strip()
    for addr in os.getenv("EMAIL_RECIPIENTS", "1932395134@qq.com").split(",")
    if addr.strip()
]
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://localhost:18000")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Send conflict notifications through the Resend API."
    )
    parser.add_argument(
        "--mode", choices=["error", "resolved"], default="error",
        help="Email template to use when --html/--text are not provided.",
    )
    parser.add_argument("--subject", help="Override the subject line.")
    parser.add_argument("--html", help="Provide a custom HTML body.")
    parser.add_argument("--text", help="Provide a custom plain-text fallback body.")
    parser.add_argument("--conflict-id", type=int, help="Conflict identifier for templates.")
    parser.add_argument(
        "--context",
        help="Optional JSON or plain text with extra context for default templates.",
    )
    parser.add_argument(
        "--to", nargs="+",
        help="Recipient email addresses. Defaults to EMAIL_RECIPIENTS or the known whitelist.",
    )
    parser.add_argument(
        "--from-address", default=DEFAULT_SENDER,
        help="Sender email address. Defaults to EMAIL_FROM or the known value.",
    )
    return parser.parse_args()


def _context_lines(raw: str | None, conflict_id: int | None) -> List[str]:
    lines: List[str] = []
    if conflict_id is not None:
        lines.append(f"冲突 ID：{conflict_id}")

    if not raw:
        return lines

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        lines.append(str(raw))
        return lines

    if isinstance(data, dict):
        for key, value in data.items():
            lines.append(f"{key}：{value}")
    elif isinstance(data, list):
        for value in data:
            lines.append(str(value))
    else:
        lines.append(str(data))
    return lines


def _default_subject(mode: str, conflict_id: int | None) -> str:
    base = "出错的内容" if mode == "error" else "冲突解除通知"
    return f"{base} - 冲突 #{conflict_id}" if conflict_id is not None else base


def _default_bodies(args: argparse.Namespace, timestamp: str) -> tuple[str, str]:
    lines = _context_lines(args.context, args.conflict_id)

    link_html = link_text = ""
    if args.conflict_id:
        link = f"{PUBLIC_BASE_URL}/ui/conflicts/{args.conflict_id}"
        link_html = f'<p><a href="{link}">点击这里查看/修正冲突 #{args.conflict_id}</a></p>'
        link_text = f"查看/修正冲突 #{args.conflict_id}：{link}"

    if lines:
        html_lines = "".join(f"<li>{line}</li>" for line in lines)
        html_details = f"<ul>{html_lines}</ul>"
        text_details = "\n".join(f"- {line}" for line in lines)
    else:
        html_details = ""
        text_details = ""

    if args.mode == "error":
        summary_html = "<p>检测到新的冲突，请尽快排查。</p>"
        summary_text = "检测到新的冲突，请尽快排查。"
    else:
        summary_html = "<p>冲突已解除，可继续关注同步情况。</p>"
        summary_text = "冲突已解除，可继续关注同步情况。"

    html = f"{summary_html}{link_html}{html_details}<p>发送时间：{timestamp}</p>"
    text_blocks = [summary_text]
    if link_text:
        text_blocks.append(link_text)
    if text_details:
        text_blocks.append(text_details)
    text_blocks.append(f"发送时间：{timestamp}")
    text = "\n\n".join(text_blocks)
    return html, text


def _prepare_payload(args: argparse.Namespace) -> dict:
    recipients = args.to or DEFAULT_RECIPIENTS
    if not recipients:
        raise RuntimeError("No recipients configured; set EMAIL_RECIPIENTS or pass --to.")

    now = datetime.now(timezone.utc).astimezone()
    timestamp = now.strftime("%Y-%m-%d %H:%M:%S %Z")

    html = args.html
    text = args.text
    if not html or not text:
        default_html, default_text = _default_bodies(args, timestamp)
        html = html or default_html
        text = text or default_text

    subject = args.subject or _default_subject(args.mode, args.conflict_id)

    payload = {
        "from": args.from_address,
        "to": recipients,
        "subject": subject,
        "html": html,
    }
    if text:
        payload["text"] = text
    return payload


def main() -> None:
    args = _parse_args()
    resend.api_key = DEFAULT_API_KEY
    if not resend.api_key:
        print("Missing Resend API key; set RESEND_API_KEY.", file=sys.stderr)
        sys.exit(1)

    payload = _prepare_payload(args)
    try:
        email = resend.Emails.send(payload)
    except Exception as exc:
        print(f"发送失败: {exc}", file=sys.stderr)
        sys.exit(2)

    print(f"发送成功，ID: {email.get('id')}")


if __name__ == "__main__":
    main()
