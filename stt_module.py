import whisper
import os


class STTProcessor:
    def __init__(self, model_size="base"):
        """
        Whisper 모델을 초기화합니다.

        Args:
            model_size: 모델 크기 (tiny, base, small, medium, large)
                       - tiny: 가장 빠르지만 정확도 낮음
                       - base: 속도와 정확도 균형 (권장)
                       - small: 더 정확하지만 느림
                       - medium/large: 가장 정확하지만 매우 느림
        """
        print(f"Whisper {model_size} 모델을 로딩 중...")
        self.model = whisper.load_model(model_size)
        print("모델 로딩 완료!")

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

        print(f"음성 파일 변환 중: {audio_file_path}")
        result = self.model.transcribe(audio_file_path, language="ko")

        return result["text"]
