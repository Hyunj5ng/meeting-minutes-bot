import os
from dotenv import load_dotenv
from openai import OpenAI


class STTProcessor:
    def __init__(self, model_size: str = None):
        """
        OpenAI Whisper API를 사용한 STT 처리기.
        로컬 모델을 로드하지 않고 API로 음성→텍스트를 수행합니다.
        model_size 매개변수는 하위 호환을 위해 받아도 무시합니다.
        """
        load_dotenv()
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError(
                "OPENAI_API_KEY가 설정되지 않았습니다. "
                ".env에 OpenAI API 키를 추가해주세요."
            )
        self.client = OpenAI(api_key=api_key)

    def transcribe(self, audio_file_path):
        """
        음성 파일을 텍스트로 변환합니다.

        Args:
            audio_file_path: 음성 파일 경로 (.mp3, .wav, .m4a 등)

        Returns:
            str: 변환된 텍스트
        """
        if not os.path.exists(audio_file_path):
            raise FileNotFoundError(f"파일을 찾을 수 없습니다: {audio_file_path}")

        print(f"음성 파일 변환 중(Whisper API): {audio_file_path}")
        with open(audio_file_path, "rb") as f:
            result = self.client.audio.transcriptions.create(
                model="whisper-1",
                file=f,
                language="ko"
            )
        return result.text
