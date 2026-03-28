from openai import AsyncOpenAI
import os
from dotenv import load_dotenv


# OpenRouter 모델 매핑 (프론트엔드 모델명 → OpenRouter 모델 ID)
MODEL_MAP = {
    # OpenAI
    "gpt-5.4-pro": "openai/gpt-5.4-pro",
    "gpt-5.4": "openai/gpt-5.4",
    "gpt-5.4-nano": "openai/gpt-5.4-nano",
    # Anthropic
    "claude-opus-4.6": "anthropic/claude-opus-4.6",
    "claude-sonnet-4.6": "anthropic/claude-sonnet-4.6",
    "claude-haiku-4.5": "anthropic/claude-haiku-4.5",
    # Google
    "gemini-2.5-pro": "google/gemini-2.5-pro-preview-03-25",
    "gemini-2.5-flash": "google/gemini-2.5-flash",
    "gemini-2.5-flash-lite": "google/gemini-2.5-flash-lite",
    # DeepSeek
    "deepseek-r1": "deepseek/deepseek-r1",
    "deepseek-chat": "deepseek/deepseek-chat",
    "deepseek-v3.2": "deepseek/deepseek-v3.2",
    # Meta Llama
    "llama-3.3-70b": "meta-llama/llama-3.3-70b-instruct",
    "llama-4-maverick": "meta-llama/llama-4-maverick",
    "llama-4-scout": "meta-llama/llama-4-scout",
}


SYSTEM_PROMPT = """당신은 전문적인 회의록 작성 비서입니다.

## 규칙
- 반드시 아래 4개 섹션을 모두 포함하세요. 어떤 섹션도 생략하지 마세요.
- 각 섹션은 "## " 마크다운 헤더로 시작합니다.
- 해당 내용이 없는 섹션에는 "- 해당 없음"이라고 작성하세요.
- 한국어로 작성하세요.
- 간결하되 핵심 내용을 빠뜨리지 마세요.
- 원문에 없는 내용을 추측하거나 지어내지 마세요.

## 출력 형식 (이 형식을 정확히 따르세요)

## 회의 주제
(1~2문장으로 회의의 주요 목적과 주제를 서술)

## 주요 논의 사항
- (토론된 핵심 내용을 bullet point로 정리)
- (각 항목은 구체적이고 명확하게)

## 결정 사항
- (회의에서 내린 결정들)
- (결정의 배경이나 이유가 언급되었다면 간략히 포함)

## 액션 아이템
- [ ] (구체적인 작업 내용) — 담당: (이름) / 기한: (날짜 또는 시기)
- [ ] (담당자나 기한이 언급되지 않았다면 해당 부분 생략 가능)
"""


class GPTSummarizer:
    def __init__(self):
        """
        OpenRouter API를 통해 여러 LLM을 사용합니다.
        .env 파일에서 OPENROUTER_API_KEY를 불러옵니다.
        """
        load_dotenv()

        api_key = os.getenv("OPENROUTER_API_KEY")
        if api_key:
            self.client = AsyncOpenAI(
                api_key=api_key,
                base_url="https://openrouter.ai/api/v1",
                default_headers={
                    "HTTP-Referer": "https://meeting-bot.jonny.kim",
                    "X-Title": "Summarying",
                },
            )
        else:
            self.client = None
            print("경고: OPENROUTER_API_KEY가 설정되지 않았습니다.")

    async def summarize(self, text, model="gpt-5-mini", context=None, past_context=None):
        """
        회의 내용을 LLM을 사용하여 정리된 회의록으로 변환합니다.

        Args:
            text: STT로 변환된 원본 텍스트
            model: 사용할 모델 (프론트엔드 기준 이름)
            context: 회의 맥락 정보 dict (project_name, meeting_title, attendees, keywords)
            past_context: RAG로 검색된 과거 회의록 요약 리스트

        Returns:
            dict: {"summary": str, "input_tokens": int, "output_tokens": int}
        """
        if not self.client:
            raise ValueError("OPENROUTER_API_KEY가 설정되지 않았습니다.")

        # OpenRouter 모델 ID로 변환 (매핑에 없으면 그대로 사용)
        router_model = MODEL_MAP.get(model, model)
        print(f"OpenRouter ({router_model})을 사용하여 회의록 작성 중...")

        prompt = self._get_prompt(text, context, past_context)

        response = await self.client.chat.completions.create(
            model=router_model,
            messages=[
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT,
                },
                {"role": "user", "content": prompt},
            ],
        )

        summary = response.choices[0].message.content
        input_tokens = response.usage.prompt_tokens if response.usage else 0
        output_tokens = response.usage.completion_tokens if response.usage else 0
        print(f"회의록 작성 완료! (입력: {input_tokens} tokens, 출력: {output_tokens} tokens)")

        return {
            "summary": summary,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens
        }

    def _get_prompt(self, text, context=None, past_context=None):
        """공통 프롬프트 생성"""
        # 맥락 정보가 있으면 프롬프트 상단에 삽입
        context_section = ""
        if context:
            lines = []
            if context.get("project_name"):
                lines.append(f"- 프로젝트: {context['project_name']}")
            if context.get("meeting_title"):
                lines.append(f"- 제목: {context['meeting_title']}")
            if context.get("attendees"):
                lines.append(f"- 참석자: {context['attendees']}")
            if context.get("keywords"):
                lines.append(f"- 키워드: {context['keywords']}")
            if lines:
                context_section = "회의 정보:\n" + "\n".join(lines) + "\n\n위 맥락을 참고하여 회의록을 작성해주세요.\n\n"

        # RAG: 과거 회의록 맥락 삽입
        past_context_section = ""
        if past_context:
            past_items = []
            for i, ctx in enumerate(past_context, 1):
                past_items.append(f"--- 과거 회의록 {i} ---\n{ctx}")
            past_context_section = (
                "참고 맥락 (이전 회의록):\n"
                + "\n\n".join(past_items)
                + "\n\n위 과거 회의 내용을 참고하여, 연속성 있는 맥락으로 이번 회의록을 작성해주세요.\n\n"
            )

        return f"""{context_section}{past_context_section}아래는 회의 중 녹음된 음성을 텍스트로 변환한 내용입니다. 시스템 프롬프트의 출력 형식에 맞춰 회의록을 작성해주세요.

<transcript>
{text}
</transcript>
"""
