import sys
import os
from datetime import datetime
from stt_module import STTProcessor
from gpt_summarizer import GPTSummarizer


def save_output(transcript, summary, output_dir="output"):
    """
    변환된 텍스트와 요약본을 파일로 저장합니다.

    Args:
        transcript: STT 원본 텍스트
        summary: GPT 요약본
        output_dir: 저장할 디렉토리
    """
    os.makedirs(output_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    transcript_path = os.path.join(output_dir, f"transcript_{timestamp}.txt")
    with open(transcript_path, "w", encoding="utf-8") as f:
        f.write(transcript)
    print(f"원본 텍스트 저장: {transcript_path}")

    summary_path = os.path.join(output_dir, f"meeting_minutes_{timestamp}.txt")
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write(summary)
    print(f"회의록 저장: {summary_path}")


def main():
    if len(sys.argv) < 2:
        print("사용법: python main.py <음성파일경로> [whisper모델크기]")
        print("예시: python main.py meeting.mp3")
        print("예시: python main.py meeting.mp3 small")
        print("\nWhisper 모델 크기 옵션: tiny, base, small, medium, large")
        print("  - tiny: 가장 빠름, 낮은 정확도")
        print("  - base: 균형잡힌 선택 (기본값)")
        print("  - small: 더 정확하지만 느림")
        print("  - medium/large: 최고 정확도, 매우 느림")
        sys.exit(1)

    audio_file = sys.argv[1]
    model_size = sys.argv[2] if len(sys.argv) > 2 else "base"

    if not os.path.exists(audio_file):
        print(f"오류: 파일을 찾을 수 없습니다 - {audio_file}")
        sys.exit(1)

    print("=" * 60)
    print("회의록 봇 시작")
    print("=" * 60)

    try:
        # 1단계: STT (음성 -> 텍스트)
        print("\n[1/3] 음성을 텍스트로 변환 중...")
        stt = STTProcessor(model_size=model_size)
        transcript = stt.transcribe(audio_file)
        print(f"\n변환된 텍스트 (첫 200자):\n{transcript[:200]}...\n")

        # 2단계: GPT 요약
        print("[2/3] GPT로 회의록 작성 중...")
        summarizer = GPTSummarizer()
        summary = summarizer.summarize(transcript)
        print(f"\n생성된 회의록:\n{summary}\n")

        # 3단계: 파일 저장
        print("[3/3] 결과 저장 중...")
        save_output(transcript, summary)

        print("\n" + "=" * 60)
        print("완료!")
        print("=" * 60)

    except Exception as e:
        print(f"\n오류 발생: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
