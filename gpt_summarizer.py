from openai import OpenAI
import os
from dotenv import load_dotenv


class GPTSummarizer:
    def __init__(self):
        """
        OpenAI GPT API를 초기화합니다.
        .env 파일에서 OPENAI_API_KEY를 불러옵니다.
        """
        load_dotenv()
        api_key = os.getenv("OPENAI_API_KEY")

        if not api_key:
            raise ValueError(
                "OPENAI_API_KEY가 설정되지 않았습니다. "
                ".env 파일에 API 키를 추가해주세요."
            )

        self.client = OpenAI(api_key=api_key)

    def summarize(self, text, model="gpt-4o-mini"):
        """
        회의 내용을 GPT를 사용하여 정리된 회의록으로 변환합니다.

        Args:
            text: STT로 변환된 원본 텍스트
            model: 사용할 GPT 모델 (기본값: gpt-4o-mini, 더 높은 품질: gpt-4o)

        Returns:
            str: 정리된 회의록
        """
        print("GPT를 사용하여 회의록 작성 중...")

        prompt = f"""
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

        response = self.client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": "당신은 전문적인 회의록 작성 비서입니다. 회의 내용을 명확하고 체계적으로 정리합니다.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
        )

        summary = response.choices[0].message.content
        print("회의록 작성 완료!")

        return summary
