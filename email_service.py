"""
이메일 발송 서비스 — Gmail SMTP 기반
환경변수: SMTP_USER (Gmail 주소), SMTP_PASSWORD (Google 앱 비밀번호)
"""
import os
import socket
import asyncio
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587

# Railway 등 클라우드 환경에서 IPv6 연결 실패 방지 — IPv4 강제
_original_getaddrinfo = socket.getaddrinfo


def _ipv4_getaddrinfo(*args, **kwargs):
    responses = _original_getaddrinfo(*args, **kwargs)
    return [r for r in responses if r[0] == socket.AF_INET] or responses


def _send_email_sync(to_email: str, subject: str, summary_text: str):
    """동기 이메일 발송 (asyncio.to_thread로 호출)"""
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_password = os.getenv("SMTP_PASSWORD", "")

    if not smtp_user or not smtp_password:
        raise ValueError("SMTP_USER 및 SMTP_PASSWORD 환경변수가 설정되지 않았습니다")

    msg = MIMEMultipart("alternative")
    msg["From"] = smtp_user
    msg["To"] = to_email
    msg["Subject"] = subject

    # 플레인 텍스트 파트
    msg.attach(MIMEText(summary_text, "plain", "utf-8"))

    # 간단한 HTML 파트 (마크다운 그대로, pre 태그로 감싸기)
    html_body = f"""\
<html>
<body>
<h2>{subject}</h2>
<pre style="font-family: sans-serif; white-space: pre-wrap; line-height: 1.6;">
{summary_text}
</pre>
<hr>
<p style="color: #888; font-size: 12px;">Summarying!에서 발송된 회의록입니다.</p>
</body>
</html>"""
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    # IPv4 강제 적용
    socket.getaddrinfo = _ipv4_getaddrinfo
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.send_message(msg)
    finally:
        socket.getaddrinfo = _original_getaddrinfo


async def send_summary_email(to_email: str, subject: str, summary_text: str):
    """비동기 이메일 발송"""
    await asyncio.to_thread(_send_email_sync, to_email, subject, summary_text)
