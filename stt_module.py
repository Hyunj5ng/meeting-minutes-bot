import os
import asyncio
import tempfile
from dotenv import load_dotenv
from groq import AsyncGroq


# Groq Whisper API 파일 크기 제한 (25MB)
MAX_FILE_SIZE = 24 * 1024 * 1024  # 24MB로 여유있게 설정
# 분할 시 청크 길이 (10분 = 600초)
CHUNK_DURATION_SEC = 600


class STTProcessor:
    def __init__(self, model_size: str = "base"):
        """
        Groq Whisper API를 사용한 STT 처리기 (비동기).

        Args:
            model_size: 사용하지 않음 (API는 단일 모델 사용). 호환성을 위해 유지.
        """
        load_dotenv()
        self.client = AsyncGroq(api_key=os.getenv("GROQ_API_KEY"))
        self.model_size = model_size
        print("Groq Whisper API 클라이언트 초기화 완료!")

    async def transcribe(self, audio_file_path):
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
            return await self._transcribe_single(audio_file_path)
        else:
            # 파일 크기가 제한 초과면 분할 처리
            print(f"파일이 24MB를 초과하여 분할 처리합니다...")
            return await self._transcribe_chunked(audio_file_path)

    async def _transcribe_single(self, audio_file_path):
        """단일 파일 변환"""
        print(f"음성 파일 변환 중 (Groq Whisper API): {audio_file_path}")

        with open(audio_file_path, "rb") as audio_file:
            transcript = await self.client.audio.transcriptions.create(
                model="whisper-large-v3-turbo",
                file=audio_file,
                language="ko"
            )

        return transcript.text

    async def _get_audio_duration(self, audio_file_path):
        """ffprobe로 오디오 길이 확인 (비동기)"""
        try:
            proc = await asyncio.create_subprocess_exec(
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                audio_file_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await proc.communicate()
            return float(stdout.decode().strip())
        except Exception as e:
            print(f"오디오 길이 확인 실패: {e}")
            return None

    async def _transcribe_chunked(self, audio_file_path):
        """ffmpeg로 스트리밍 분할하여 변환 (비동기)"""

        # 오디오 길이 확인
        duration = await self._get_audio_duration(audio_file_path)
        if duration:
            print(f"총 오디오 길이: {duration/60:.1f}분")
            num_chunks = int(duration // CHUNK_DURATION_SEC) + 1
            print(f"예상 청크 수: {num_chunks}개")

        transcripts = []
        chunk_num = 0

        with tempfile.TemporaryDirectory() as temp_dir:
            # ffmpeg로 10분 단위로 분할 (비동기)
            output_pattern = os.path.join(temp_dir, "chunk_%03d.mp3")

            print("ffmpeg로 오디오 분할 중...")
            proc = await asyncio.create_subprocess_exec(
                "ffmpeg", "-i", audio_file_path,
                "-f", "segment",
                "-segment_time", str(CHUNK_DURATION_SEC),
                "-c:a", "libmp3lame",
                "-b:a", "64k",  # 낮은 비트레이트로 파일 크기 줄임
                "-ac", "1",     # 모노로 변환 (파일 크기 절반)
                "-ar", "16000", # 16kHz 샘플레이트 (음성에 충분)
                "-y",
                output_pattern,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await proc.communicate()

            # 생성된 청크 파일들 처리
            chunk_files = sorted([
                f for f in os.listdir(temp_dir)
                if f.startswith("chunk_") and f.endswith(".mp3")
            ])

            total_chunks = len(chunk_files)
            print(f"총 {total_chunks}개의 청크 생성됨")

            for chunk_file in chunk_files:
                chunk_num += 1
                chunk_path = os.path.join(temp_dir, chunk_file)
                chunk_size = os.path.getsize(chunk_path)

                print(f"청크 {chunk_num}/{total_chunks} 처리 중... ({chunk_size / (1024*1024):.2f}MB)")

                # Groq Whisper API 호출 (비동기)
                with open(chunk_path, "rb") as audio_file:
                    transcript = await self.client.audio.transcriptions.create(
                        model="whisper-large-v3-turbo",
                        file=audio_file,
                        language="ko"
                    )
                transcripts.append(transcript.text)
                print(f"청크 {chunk_num}/{total_chunks} 완료!")

                # 처리 완료된 청크 파일 즉시 삭제 (메모리/디스크 절약)
                os.remove(chunk_path)

        # 모든 텍스트 합치기
        full_transcript = " ".join(transcripts)
        print(f"총 {total_chunks}개 청크 변환 완료!")

        return full_transcript
