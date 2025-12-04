import os
from dotenv import load_dotenv
import whisper


class STTProcessor:
    def __init__(self, model_size: str = "base"):
        """
        OpenAI Whisper 로컬 모델을 사용한 STT 처리기.

        Args:
            model_size: Whisper 모델 크기 (tiny, base, small, medium, large)
                       - tiny: 가장 빠름, 정확도 낮음 (~1GB RAM)
                       - base: 빠르고 적절한 정확도 (~1GB RAM) [기본값]
                       - small: 균형잡힌 속도/정확도 (~2GB RAM)
                       - medium: 느리지만 정확함 (~5GB RAM)
                       - large: 가장 느리지만 가장 정확함 (~10GB RAM)
        """
        load_dotenv()
        self.model_size = model_size
        print(f"Whisper 모델 로딩 중 (크기: {model_size})...")
        self.model = whisper.load_model(model_size)
        print(f"Whisper 모델 로딩 완료!")

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

        print(f"음성 파일 변환 중 (Whisper {self.model_size}): {audio_file_path}")
        result = self.model.transcribe(audio_file_path, language="ko")
        return result["text"]
