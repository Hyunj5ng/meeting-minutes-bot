from openai import AsyncOpenAI
import anthropic
import os
from dotenv import load_dotenv


# Claude 모델 목록
CLAUDE_MODELS = ["claude-sonnet-4-5-20250929", "claude-haiku-4-5-20251001"]

# 시스템 프롬프트
SYSTEM_PROMPT = """당신은 전문적인 회의록 작성 비서입니다.

핵심 원칙:
- 회의에서 논의된 세부 내용을 절대 생략하지 않습니다.
- 모든 발언과 논의 사항을 빠짐없이 포착하되, 체계적으로 구조화합니다.
- 원본 텍스트에 등장하는 구체적인 수치, 이름, 날짜, 기술 용어 등은 반드시 포함합니다.
- bullet point 계층 구조를 활용하여 가독성을 높입니다."""


class GPTSummarizer:
    def __init__(self):
        """
        OpenAI GPT API와 Anthropic Claude API를 초기화합니다 (비동기).
        .env 파일에서 API 키를 불러옵니다.
        """
        load_dotenv()

        # OpenAI 클라이언트 (비동기)
        openai_api_key = os.getenv("OPENAI_API_KEY")
        if openai_api_key:
            self.openai_client = AsyncOpenAI(api_key=openai_api_key)
        else:
            self.openai_client = None
            print("경고: OPENAI_API_KEY가 설정되지 않았습니다.")

        # Anthropic 클라이언트 (비동기)
        anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
        if anthropic_api_key:
            self.anthropic_client = anthropic.AsyncAnthropic(api_key=anthropic_api_key)
        else:
            self.anthropic_client = None
            print("경고: ANTHROPIC_API_KEY가 설정되지 않았습니다.")

    async def summarize(self, text, model="gpt-5-mini", context=None, past_context=None):
        """
        회의 내용을 LLM을 사용하여 정리된 회의록으로 변환합니다.

        Args:
            text: STT로 변환된 원본 텍스트
            model: 사용할 모델
            context: 회의 맥락 정보 dict (project_name, meeting_title, attendees, keywords)
            past_context: RAG로 검색된 과거 회의록 요약 리스트

        Returns:
            dict: {"summary": str, "input_tokens": int, "output_tokens": int}
        """
        # Claude 모델인지 확인
        if model in CLAUDE_MODELS:
            return await self._summarize_with_claude(text, model, context, past_context)
        else:
            return await self._summarize_with_openai(text, model, context, past_context)

    async def _summarize_with_openai(self, text, model, context=None, past_context=None):
        """OpenAI GPT로 요약 (비동기)"""
        if not self.openai_client:
            raise ValueError("OPENAI_API_KEY가 설정되지 않았습니다.")

        print(f"OpenAI {model}을 사용하여 회의록 작성 중...")

        prompt = self._get_prompt(text, context, past_context)

        api_params = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT,
                },
                {"role": "user", "content": prompt},
            ],
        }

        # GPT-5 모델이 아닌 경우에만 temperature 설정
        if not model.startswith("gpt-5"):
            api_params["temperature"] = 0.3

        response = await self.openai_client.chat.completions.create(**api_params)

        summary = response.choices[0].message.content
        input_tokens = response.usage.prompt_tokens
        output_tokens = response.usage.completion_tokens
        print(f"회의록 작성 완료! (입력: {input_tokens} tokens, 출력: {output_tokens} tokens)")

        return {
            "summary": summary,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens
        }

    async def _summarize_with_claude(self, text, model, context=None, past_context=None):
        """Anthropic Claude로 요약 (비동기)"""
        if not self.anthropic_client:
            raise ValueError("ANTHROPIC_API_KEY가 설정되지 않았습니다.")

        print(f"Claude {model}을 사용하여 회의록 작성 중...")

        prompt = self._get_prompt(text, context, past_context)

        response = await self.anthropic_client.messages.create(
            model=model,
            max_tokens=8192,
            system=SYSTEM_PROMPT,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )

        summary = response.content[0].text
        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens
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

        return f"""{context_section}{past_context_section}다음은 회의 중 녹음된 음성을 텍스트로 변환한 내용입니다.
이를 읽기 쉽고 체계적인 회의록으로 정리해주세요.

**중요 지침:**
- 원본 텍스트에 포함된 세부 논의 내용, 구체적인 사례, 수치, 의견 등을 빠뜨리지 마세요.
- 각 항목은 bullet point(•)와 하위 bullet point(-)를 사용하여 계층적으로 정리하세요.
- 누가 무엇을 말했는지 파악 가능하면 발언자를 명시하세요.
- 단순 요약이 아니라, 논의의 맥락과 근거까지 포함하세요.

다음 형식으로 작성해주세요:

## 1. 회의 주제
회의의 주요 목적과 주제를 간결하게 서술

## 2. 주요 논의 사항
논의된 모든 내용을 주제별로 분류하여 정리합니다. 각 주제 아래 세부 내용을 빠짐없이 기록하세요.
• 주요 주제 1
  - 세부 논의 내용
  - 구체적 수치나 사례
  - 관련 의견 및 반론
• 주요 주제 2
  - ...

## 3. 결정 사항
회의에서 확정된 결정들을 명확하게 나열
• 결정 1
• 결정 2

## 4. 액션 아이템
향후 진행해야 할 작업들 (담당자, 기한이 언급되었다면 반드시 포함)
• [담당자] 작업 내용 (기한: ~)

원본 텍스트:
{text}
"""
