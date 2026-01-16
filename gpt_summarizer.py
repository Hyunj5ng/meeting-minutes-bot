from openai import OpenAI
import anthropic
import os
from dotenv import load_dotenv


# Claude 모델 목록
CLAUDE_MODELS = ["claude-sonnet-4-5-20250929", "claude-haiku-4-5-20251001"]


class GPTSummarizer:
    def __init__(self):
        """
        OpenAI GPT API와 Anthropic Claude API를 초기화합니다.
        .env 파일에서 API 키를 불러옵니다.
        """
        load_dotenv()

        # OpenAI 클라이언트
        openai_api_key = os.getenv("OPENAI_API_KEY")
        if openai_api_key:
            self.openai_client = OpenAI(api_key=openai_api_key)
        else:
            self.openai_client = None
            print("경고: OPENAI_API_KEY가 설정되지 않았습니다.")

        # Anthropic 클라이언트
        anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
        if anthropic_api_key:
            self.anthropic_client = anthropic.Anthropic(api_key=anthropic_api_key)
        else:
            self.anthropic_client = None
            print("경고: ANTHROPIC_API_KEY가 설정되지 않았습니다.")

    def summarize(self, text, model="gpt-5-mini"):
        """
        회의 내용을 LLM을 사용하여 정리된 회의록으로 변환합니다.

        Args:
            text: STT로 변환된 원본 텍스트
            model: 사용할 모델
                   - OpenAI: gpt-5.1, gpt-5, gpt-5-mini, gpt-5-nano, gpt-4.1
                   - Claude: claude-sonnet-4-5-20250929, claude-haiku-4-5-20251001

        Returns:
            str: 정리된 회의록
        """
        # Claude 모델인지 확인
        if model in CLAUDE_MODELS:
            return self._summarize_with_claude(text, model)
        else:
            return self._summarize_with_openai(text, model)

    def _summarize_with_openai(self, text, model):
        """OpenAI GPT로 요약"""
        if not self.openai_client:
            raise ValueError("OPENAI_API_KEY가 설정되지 않았습니다.")

        print(f"OpenAI {model}을 사용하여 회의록 작성 중...")

        prompt = self._get_prompt(text)

        api_params = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": "당신은 전문적인 회의록 작성 비서입니다. 회의 내용을 명확하고 체계적으로 정리합니다.",
                },
                {"role": "user", "content": prompt},
            ],
        }

        # GPT-5 모델이 아닌 경우에만 temperature 설정
        if not model.startswith("gpt-5"):
            api_params["temperature"] = 0.3

        response = self.openai_client.chat.completions.create(**api_params)

        summary = response.choices[0].message.content
        print("회의록 작성 완료!")

        return summary

    def _summarize_with_claude(self, text, model):
        """Anthropic Claude로 요약"""
        if not self.anthropic_client:
            raise ValueError("ANTHROPIC_API_KEY가 설정되지 않았습니다.")

        print(f"Claude {model}을 사용하여 회의록 작성 중...")

        prompt = self._get_prompt(text)

        response = self.anthropic_client.messages.create(
            model=model,
            max_tokens=4096,
            system="당신은 전문적인 회의록 작성 비서입니다. 회의 내용을 명확하고 체계적으로 정리합니다.",
            messages=[
                {"role": "user", "content": prompt}
            ]
        )

        summary = response.content[0].text
        print("회의록 작성 완료!")

        return summary

    def _get_prompt(self, text):
        """공통 프롬프트 생성"""
        return f"""
다음은 회의 중 녹음된 음성을 텍스트로 변환한 내용입니다.
이를 읽기 쉽고 체계적인 회의록으로 정리해주세요.

다음 형식으로 작성해주세요:
1. **회의 주제**: 회의의 주요 목적과 주제
2. **주요 논의 사항**: 토론된 핵심 내용들을 bullet point로 정리
3. **결정 사항**: 회의에서 내린 결정들
4. **액션 아이템**: 향후 진행해야 할 작업들 (담당자가 언급되었다면 포함)

원본 텍스트:
{text}
"""
