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


# 시스템 프롬프트
SYSTEM_PROMPT = """당신은 전문적인 회의록 작성 비서입니다.

핵심 원칙:
- 회의에서 논의된 세부 내용을 절대 생략하지 않습니다.
- 모든 발언과 논의 사항을 빠짐없이 포착하되, 체계적으로 구조화합니다.
- 원본 텍스트에 등장하는 구체적인 수치, 이름, 날짜, 기술 용어 등은 반드시 포함합니다.
- 원문에 없는 내용을 추측하거나 지어내지 마세요.
- 반드시 아래 4개 섹션을 모두 포함하세요. 어떤 섹션도 생략하지 마세요.
- 한국어로 작성하세요.

화자 구분 원칙 (참석자 목록이 주어진 경우):
- STT 원문에는 화자 표시가 없습니다. 발언 내용("제가 ~할게요", "OO님 의견은?"), 호명, 담당 업무, 프로젝트 맥락의 인물 정보를 단서로 누가 한 말인지 최대한 추론하세요.
- 주요 의견·결정·약속은 "(이름)" 형태로 화자를 명시하세요. 예) - 베타 출시는 6/17로 확정 (현종)
- 확신이 없으면 이름 뒤에 "(추정)"을 붙이고, 단서가 전혀 없으면 화자 표기를 생략하세요. 틀린 귀속보다 생략이 낫습니다.
- 액션 아이템의 담당자는 발언 맥락에서 최대한 찾아 채우세요.

마크다운 서식 규칙 (Notion 호환 — 반드시 준수):
- 최상위 섹션은 "## " (h2)로 표기합니다. 예: ## 회의 주제
- 섹션 내부의 주제/소단원은 "### " (h3)로 표기합니다. 볼드 불릿(`- **제목**`)으로 대신하지 마세요.
- 각 h3 아래의 세부 내용은 평탄한 "- " 불릿 한 단계만 사용합니다. 2단계 들여쓰기(불릿 안의 불릿)는 피하세요.
- "•" 같은 유니코드 불릿 대신 표준 마크다운 "- "만 사용합니다.
- 해당 내용이 없는 섹션에는 "- 해당 없음"이라고 작성하세요.

## 출력 형식 (이 형식을 정확히 따르세요)

## 회의 주제
(1~2문장으로 회의의 주요 목적과 주제를 서술)

## 주요 논의 사항
(논의된 모든 내용을 주제별로 분류하여 정리. 각 주제는 ### 헤더로, 세부는 평탄한 - 불릿)

### 주요 주제 1
- 세부 논의 내용
- 구체적 수치나 사례
- 관련 의견 및 반론

### 주요 주제 2
- ...

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

    async def summarize(self, text, model="gpt-5-mini", context=None, past_context=None, glossary=None,
                        project_memory=None, style_rules=None):
        """
        회의 내용을 LLM을 사용하여 정리된 회의록으로 변환합니다.

        Args:
            text: STT로 변환된 원본 텍스트
            model: 사용할 모델 (프론트엔드 기준 이름)
            context: 회의 맥락 정보 dict (project_name, meeting_title, attendees, keywords)
            past_context: RAG로 검색된 과거 회의록 요약 리스트
            glossary: 컨텍스트 글로서리 리스트 [{term, correction, note}]
                      개인+프로젝트 컨텍스트 통합본. STT 오타/표기 교정에 사용.
            project_memory: 프로젝트 누적 메모리 (결정사항/진행 주제/인물·역할)
            style_rules: 사용자 스타일 선호 문자열 리스트 (수정 패턴에서 학습됨)

        Returns:
            dict: {"summary": str, "input_tokens": int, "output_tokens": int}
        """
        if not self.client:
            raise ValueError("OPENROUTER_API_KEY가 설정되지 않았습니다.")

        # OpenRouter 모델 ID로 변환 (매핑에 없으면 그대로 사용)
        router_model = MODEL_MAP.get(model, model)
        print(f"OpenRouter ({router_model})을 사용하여 회의록 작성 중...")

        prompt = self._get_prompt(text, context, past_context, glossary, project_memory, style_rules)

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

    def _get_prompt(self, text, context=None, past_context=None, glossary=None,
                    project_memory=None, style_rules=None):
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

        # 글로서리 (개인 + 프로젝트 컨텍스트) — STT 표기 교정용
        glossary_section = ""
        if glossary:
            glossary_lines = []
            for item in glossary:
                term = (item.get("term") or "").strip()
                correction = (item.get("correction") or "").strip()
                note = (item.get("note") or "").strip()
                if not term or not correction:
                    continue
                line = f'- "{term}" → "{correction}"'
                if note:
                    line += f" ({note})"
                glossary_lines.append(line)
            if glossary_lines:
                glossary_section = (
                    "알려진 표기/용어 (반드시 적용):\n"
                    "STT가 음성을 텍스트로 변환할 때 인명/고유명사를 잘못 표기하는 경우가 많습니다. "
                    "아래 목록의 잘못된 표기가 본문에 등장하면 올바른 표기로 자동 치환해서 회의록을 작성하세요.\n"
                    + "\n".join(glossary_lines)
                    + "\n\n"
                )

        # 프로젝트 누적 메모리 — 회의가 쌓일수록 깊어지는 장기 기억
        memory_section = ""
        if project_memory and project_memory.strip():
            memory_section = (
                "프로젝트 누적 메모리 (이 프로젝트에서 지금까지 합의/논의된 내용의 요약):\n"
                + project_memory.strip()
                + "\n\n위 메모리를 활용하세요: 등장 인물의 역할로 화자를 추론하고, 과거 결정사항과 이어지는 논의는 그 맥락을 반영하며, "
                "이전 결정이 뒤집히면 변경되었음을 명시하세요. 단, 이번 회의에서 언급되지 않은 메모리 내용을 회의록에 끼워 넣지는 마세요.\n\n"
            )

        # 사용자 스타일 선호 — 과거 수정 패턴에서 학습됨
        style_section = ""
        if style_rules:
            rules = [r.strip() for r in style_rules if r and r.strip()]
            if rules:
                style_section = (
                    "사용자 회의록 스타일 선호 (과거 수정 패턴에서 학습됨 — 형식 충돌 시 시스템 프롬프트의 섹션 구조는 유지하되 그 안에서 반영):\n"
                    + "\n".join(f"- {r}" for r in rules)
                    + "\n\n"
                )

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

        return f"""{context_section}{memory_section}{glossary_section}{style_section}{past_context_section}아래는 회의 중 녹음된 음성을 텍스트로 변환한 내용입니다. 시스템 프롬프트의 출력 형식에 맞춰 회의록을 작성해주세요.

**중요 지침:**
- 원본 텍스트에 포함된 세부 논의 내용, 구체적인 사례, 수치, 의견 등을 빠뜨리지 마세요.
- 각 항목은 bullet point(•)와 하위 bullet point(-)를 사용하여 계층적으로 정리하세요.
- 누가 무엇을 말했는지 파악 가능하면 발언자를 명시하세요.
- 단순 요약이 아니라, 논의의 맥락과 근거까지 포함하세요.

<transcript>
{text}
</transcript>
"""
