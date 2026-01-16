import os
import tempfile
from dotenv import load_dotenv
from openai import OpenAI
from pydub import AudioSegment


# OpenAI Whisper API 파일 크기 제한 (25MB)
MAX_FILE_SIZE = 24 * 1024 * 1024  # 24MB로 여유있게 설정
# 분할 시 청크 길이 (10분)
CHUNK_DURATION_MS = 10 * 60 * 1000


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
        25MB 초과 시 자동으로 분할하여 처리합니다.

        Args:
            audio_file_path: 음성 파일 경로 (.mp3, .wav, .m4a 등)

        Returns:
            str: 변환된 텍스트
        """
        if not os.path.exists(audio_file_path):
            raise FileNotFoundError(f"파일을 찾을 수 없습니다: {audio_file_path}")

        file_size = os.path.getsize(audio_file_path)
        print(f"음성 파일 크기: {file_size / (1024*1024):.2f}MB")

        if file_size <= MAX_FILE_SIZE:
            # 파일 크기가 제한 이하면 그대로 처리
            return self._transcribe_single(audio_file_path)
        else:
            # 파일 크기가 제한 초과면 분할 처리
            print(f"파일이 25MB를 초과하여 분할 처리합니다...")
            return self._transcribe_chunked(audio_file_path)

    def _transcribe_single(self, audio_file_path):
        """단일 파일 변환"""
        print(f"음성 파일 변환 중 (OpenAI Whisper API): {audio_file_path}")

        with open(audio_file_path, "rb") as audio_file:
            transcript = self.client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                language="ko"
            )

        return transcript.text

    def _transcribe_chunked(self, audio_file_path):
        """큰 파일을 분할하여 변환"""
        # 오디오 파일 로드
        print(f"오디오 파일 로딩 중...")
        audio = AudioSegment.from_file(audio_file_path)
        total_duration_ms = len(audio)
        total_duration_min = total_duration_ms / 1000 / 60
        print(f"총 오디오 길이: {total_duration_min:.1f}분")

        # 청크로 분할
        chunks = []
        start = 0
        chunk_num = 1
        while start < total_duration_ms:
            end = min(start + CHUNK_DURATION_MS, total_duration_ms)
            chunks.append((chunk_num, audio[start:end]))
            start = end
            chunk_num += 1

        print(f"총 {len(chunks)}개의 청크로 분할됨")

        # 각 청크 처리
        transcripts = []
        with tempfile.TemporaryDirectory() as temp_dir:
            for chunk_num, chunk in chunks:
                chunk_path = os.path.join(temp_dir, f"chunk_{chunk_num}.mp3")

                # 청크를 mp3로 저장 (압축률 좋음)
                chunk.export(chunk_path, format="mp3", bitrate="128k")
                chunk_size = os.path.getsize(chunk_path)
                print(f"청크 {chunk_num}/{len(chunks)} 처리 중... ({chunk_size / (1024*1024):.2f}MB)")

                # Whisper API 호출
                with open(chunk_path, "rb") as audio_file:
                    transcript = self.client.audio.transcriptions.create(
                        model="whisper-1",
                        file=audio_file,
                        language="ko"
                    )
                transcripts.append(transcript.text)
                print(f"청크 {chunk_num}/{len(chunks)} 완료!")

        # 모든 텍스트 합치기
        full_transcript = " ".join(transcripts)
        print(f"총 {len(chunks)}개 청크 변환 완료!")

        return full_transcript
