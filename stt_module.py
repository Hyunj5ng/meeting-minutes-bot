import os
from dotenv import load_dotenv
from openai import OpenAI


class STTProcessor:
    def __init__(self, model_size: str = "base"):
        """
        OpenAI Whisper API를 사용한 STT 처리기.

        Args:
            model_size: 사용하지 않음 (API는 단일 모델 사용). 호환성을 위해 유지.
        """
        load_dotenv()
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.model_size = model_size
        print("OpenAI Whisper API 클라이언트 초기화 완료!")

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

        print(f"음성 파일 변환 중 (OpenAI Whisper API): {audio_file_path}")

        with open(audio_file_path, "rb") as audio_file:
            transcript = self.client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                language="ko"
            )

        return transcript.text
