"""
이메일 발송 서비스 — Resend HTTP API 기반
환경변수: RESEND_API_KEY
"""
import os
import asyncio
import resend


def _send_email_sync(to_email: str, subject: str, summary_text: str):
    """동기 이메일 발송 (asyncio.to_thread로 호출)"""
    api_key = os.getenv("RESEND_API_KEY", "")
    if not api_key:
        raise ValueError("RESEND_API_KEY 환경변수가 설정되지 않았습니다")

    resend.api_key = api_key

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

    resend.Emails.send({
        "from": "Summarying! <noreply@meeting-bot.jonny.kim>",
        "to": [to_email],
        "subject": subject,
        "html": html_body,
        "text": summary_text,
    })


async def send_summary_email(to_email: str, subject: str, summary_text: str):
    """비동기 이메일 발송"""
    await asyncio.to_thread(_send_email_sync, to_email, subject, summary_text)
