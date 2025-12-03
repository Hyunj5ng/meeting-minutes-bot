"""
데이터베이스 내용 확인 스크립트
"""
from database import SessionLocal
from models import MeetingRecord
from datetime import datetime

def view_all_records():
    """모든 레코드 조회"""
    db = SessionLocal()
    try:
        records = db.query(MeetingRecord).order_by(MeetingRecord.created_at.desc()).all()

        if not records:
            print("📭 저장된 회의록이 없습니다.")
            return

        print(f"\n📊 총 {len(records)}개의 회의록이 저장되어 있습니다.\n")
        print("=" * 100)

        for record in records:
            print(f"\n🆔 ID: {record.id}")
            print(f"📁 파일명: {record.filename}")
            print(f"📦 파일 크기: {record.file_size / 1024 / 1024:.2f} MB")

            if record.audio_duration:
                minutes = int(record.audio_duration // 60)
                seconds = int(record.audio_duration % 60)
                print(f"⏱️  오디오 길이: {minutes}분 {seconds}초")

            print(f"🎙️  Whisper 모델: {record.whisper_model}")

            if record.stt_processing_time:
                print(f"⚡ STT 처리 시간: {record.stt_processing_time:.2f}초")

            if record.gpt_model:
                print(f"🤖 GPT 모델: {record.gpt_model}")
                if record.gpt_processing_time:
                    print(f"⚡ GPT 처리 시간: {record.gpt_processing_time:.2f}초")
            else:
                print(f"⚠️  회의록 미생성 (STT만 완료)")

            print(f"📅 생성일: {record.created_at.strftime('%Y-%m-%d %H:%M:%S')}")

            # 텍스트 미리보기
            transcript_preview = record.transcript[:100] + "..." if len(record.transcript) > 100 else record.transcript
            print(f"📝 텍스트 미리보기: {transcript_preview}")

            if record.summary:
                summary_preview = record.summary[:100] + "..." if len(record.summary) > 100 else record.summary
                print(f"📄 회의록 미리보기: {summary_preview}")

            print("=" * 100)

    finally:
        db.close()

def view_latest():
    """최근 레코드만 조회"""
    db = SessionLocal()
    try:
        record = db.query(MeetingRecord).order_by(MeetingRecord.created_at.desc()).first()

        if not record:
            print("📭 저장된 회의록이 없습니다.")
            return

        print("\n🆕 가장 최근 회의록:\n")
        print("=" * 100)
        print(f"🆔 ID: {record.id}")
        print(f"📁 파일명: {record.filename}")
        print(f"📝 전체 텍스트:\n{record.transcript}\n")

        if record.summary:
            print(f"📄 회의록:\n{record.summary}\n")
        else:
            print("⚠️  회의록이 아직 생성되지 않았습니다.\n")

        print("=" * 100)

    finally:
        db.close()

def search_records(keyword):
    """키워드로 검색"""
    db = SessionLocal()
    try:
        search_pattern = f"%{keyword}%"
        records = db.query(MeetingRecord).filter(
            (MeetingRecord.filename.ilike(search_pattern)) |
            (MeetingRecord.transcript.ilike(search_pattern)) |
            (MeetingRecord.summary.ilike(search_pattern))
        ).all()

        if not records:
            print(f"🔍 '{keyword}' 검색 결과가 없습니다.")
            return

        print(f"\n🔍 '{keyword}' 검색 결과: {len(records)}개\n")
        print("=" * 100)

        for record in records:
            print(f"🆔 ID: {record.id} | 📁 {record.filename}")
            print(f"📅 {record.created_at.strftime('%Y-%m-%d %H:%M:%S')}")
            print("=" * 100)

    finally:
        db.close()

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        command = sys.argv[1]

        if command == "latest":
            view_latest()
        elif command == "search" and len(sys.argv) > 2:
            keyword = sys.argv[2]
            search_records(keyword)
        else:
            print("사용법:")
            print("  python view_db.py           # 모든 레코드 조회")
            print("  python view_db.py latest    # 최근 레코드 조회")
            print("  python view_db.py search 키워드  # 키워드 검색")
    else:
        view_all_records()
