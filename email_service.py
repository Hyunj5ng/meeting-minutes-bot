"""
이메일 발송 서비스 — Resend HTTP API 기반
환경변수: RESEND_API_KEY, APP_BASE_URL (수정하러 가기 딥링크용)
"""
import os
import asyncio
import html as html_lib
import resend

# 이메일의 "수정하러 가기" 버튼이 가리킬 앱 주소
APP_BASE_URL = os.getenv("APP_BASE_URL", "https://meeting-bot.jonny.kim").rstrip("/")


def _send_email_sync(to_email: str, subject: str, summary_text: str, summary_id: int | None = None):
    """동기 이메일 발송 (asyncio.to_thread로 호출)"""
    api_key = os.getenv("RESEND_API_KEY", "")
    if not api_key:
        raise ValueError("RESEND_API_KEY 환경변수가 설정되지 않았습니다")

    resend.api_key = api_key

    # 수정하러 가기 버튼 (summary_id가 있을 때만) — 앱의 해시 딥링크로 이동
    edit_button = ""
    if summary_id is not None:
        edit_url = f"{APP_BASE_URL}/app#summary/{summary_id}"
        edit_button = f"""\
<table role="presentation" cellpadding="0" cellspacing="0" style="margin: 20px 0;">
  <tr>
    <td style="background: #0D9488; border-radius: 10px;">
      <a href="{edit_url}" target="_blank"
         style="display: inline-block; padding: 11px 22px; color: #ffffff; text-decoration: none; font-weight: 700; font-size: 14px;">
        ✏️ 수정하러 가기
      </a>
    </td>
  </tr>
</table>
<p style="color: #888; font-size: 12px;">버튼이 안 보이면 이 주소로 접속하세요: {edit_url}</p>"""

    escaped_summary = html_lib.escape(summary_text)
    html_body = f"""\
<html>
<body style="font-family: -apple-system, sans-serif; color: #182B28; max-width: 640px; margin: 0 auto;">
<h2 style="color: #0F766E;">{html_lib.escape(subject)}</h2>
{edit_button}
<pre style="font-family: sans-serif; white-space: pre-wrap; line-height: 1.6; background: #F6F8F8; border: 1px solid #E3E9E8; border-radius: 10px; padding: 16px;">
{escaped_summary}
</pre>
<hr style="border: none; border-top: 1px solid #E3E9E8;">
<p style="color: #888; font-size: 12px;">Summarying!에서 발송된 회의록입니다. 회의록을 수정하면 AI가 용어·스타일을 학습해 다음 회의록이 더 정확해져요.</p>
</body>
</html>"""

    resend.Emails.send({
        "from": "Summarying! <noreply@meeting-bot.jonny.kim>",
        "to": [to_email],
        "subject": subject,
        "html": html_body,
        "text": summary_text,
    })


async def send_summary_email(to_email: str, subject: str, summary_text: str, summary_id: int | None = None):
    """비동기 이메일 발송. summary_id를 주면 '수정하러 가기' 딥링크 버튼이 포함된다."""
    await asyncio.to_thread(_send_email_sync, to_email, subject, summary_text, summary_id)


async def send_summary_email_background(to_email: str, subject: str, summary_text: str, summary_id: int | None = None):
    """BackgroundTask용 — 실패해도 요약 생성에 영향 없도록 조용히 로그만 남긴다."""
    try:
        await send_summary_email(to_email, subject, summary_text, summary_id)
        print(f"[Email] 자동 발송 완료 → {to_email} (summary_id={summary_id})")
    except Exception as e:
        print(f"[Email] 자동 발송 실패 (무시): {e}")
