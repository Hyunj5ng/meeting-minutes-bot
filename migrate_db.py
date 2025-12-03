"""
데이터베이스 마이그레이션 스크립트
기존 meeting_records 테이블을 transcript_records와 summary_records로 분리
"""
from database import SessionLocal, engine
from models import TranscriptRecord, SummaryRecord, Base
from sqlalchemy import text, inspect
import sys


def check_old_schema_exists():
    """기존 스키마(meeting_records) 존재 여부 확인"""
    inspector = inspect(engine)
    return 'meeting_records' in inspector.get_table_names()


def migrate_data():
    """기존 데이터를 새 스키마로 마이그레이션"""
    db = SessionLocal()

    try:
        print("=" * 80)
        print("데이터베이스 마이그레이션 시작")
        print("=" * 80)

        # 1. 기존 스키마 확인
        if not check_old_schema_exists():
            print("\n✅ 기존 meeting_records 테이블이 없습니다.")
            print("   새로운 스키마로 테이블을 생성합니다...\n")
            Base.metadata.create_all(bind=engine)
            print("✅ 새 테이블 생성 완료!")
            print("   - transcript_records")
            print("   - summary_records")
            return

        print("\n📋 기존 meeting_records 테이블 발견!")

        # 2. 기존 데이터 조회
        result = db.execute(text("SELECT COUNT(*) FROM meeting_records"))
        count = result.scalar()

        print(f"   총 {count}개의 레코드가 있습니다.")

        if count == 0:
            print("\n⚠️  데이터가 없으므로 테이블만 재생성합니다.\n")
            # 기존 테이블 삭제
            db.execute(text("DROP TABLE IF EXISTS meeting_records"))
            db.commit()
            # 새 테이블 생성
            Base.metadata.create_all(bind=engine)
            print("✅ 새 테이블 생성 완료!")
            return

        # 3. 사용자 확인
        print("\n⚠️  주의: 기존 데이터를 새 스키마로 마이그레이션합니다.")
        print("   - transcript_records: STT 변환 데이터만 저장")
        print("   - summary_records: GPT 요약 데이터만 저장 (기존 데이터에서 생성)")
        response = input("\n계속하시겠습니까? (y/N): ")

        if response.lower() != 'y':
            print("\n❌ 마이그레이션이 취소되었습니다.")
            return

        print("\n🔄 데이터 마이그레이션 중...\n")

        # 4. 기존 데이터 읽기
        old_records = db.execute(text("""
            SELECT id, filename, file_size, audio_duration, transcript,
                   whisper_model, stt_processing_time, summary,
                   gpt_model, gpt_processing_time, created_at
            FROM meeting_records
            ORDER BY id
        """)).fetchall()

        # 5. 새 테이블 생성
        Base.metadata.create_all(bind=engine)
        print(f"✅ 새 테이블 생성 완료 (transcript_records, summary_records)")

        # 6. 데이터 마이그레이션
        transcript_count = 0
        summary_count = 0

        for old_record in old_records:
            # TranscriptRecord 생성
            transcript_record = TranscriptRecord(
                filename=old_record.filename,
                file_size=old_record.file_size,
                audio_duration=old_record.audio_duration,
                transcript=old_record.transcript,
                whisper_model=old_record.whisper_model or "base",
                stt_processing_time=old_record.stt_processing_time,
                created_at=old_record.created_at
            )
            db.add(transcript_record)
            db.flush()  # ID 생성
            transcript_count += 1

            print(f"  ✓ Transcript #{transcript_record.id}: {old_record.filename}")

            # Summary가 있으면 SummaryRecord 생성
            if old_record.summary and old_record.gpt_model:
                summary_record = SummaryRecord(
                    transcript_id=transcript_record.id,
                    summary=old_record.summary,
                    gpt_model=old_record.gpt_model,
                    gpt_processing_time=old_record.gpt_processing_time,
                    created_at=old_record.created_at
                )
                db.add(summary_record)
                summary_count += 1
                print(f"    └─ Summary #{summary_record.id}: {old_record.gpt_model}")

        db.commit()

        print(f"\n✅ 데이터 마이그레이션 완료!")
        print(f"   - Transcript 레코드: {transcript_count}개")
        print(f"   - Summary 레코드: {summary_count}개")

        # 7. 기존 테이블 백업 및 삭제
        print("\n🗑️  기존 테이블 정리 중...")

        # 백업 테이블 생성
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS meeting_records_backup AS
            SELECT * FROM meeting_records
        """))
        print("  ✓ meeting_records를 meeting_records_backup으로 백업")

        # 기존 테이블 삭제
        db.execute(text("DROP TABLE meeting_records"))
        db.commit()
        print("  ✓ meeting_records 테이블 삭제")

        print("\n" + "=" * 80)
        print("✅ 마이그레이션 완료!")
        print("=" * 80)
        print("\n📌 참고:")
        print("  - 기존 데이터는 meeting_records_backup 테이블에 백업되어 있습니다.")
        print("  - 문제가 없다면 나중에 'DROP TABLE meeting_records_backup'으로 삭제하세요.")
        print("  - VS Code의 SQLite Viewer로 데이터를 확인할 수 있습니다.")

    except Exception as e:
        db.rollback()
        print(f"\n❌ 오류 발생: {str(e)}")
        print("   데이터베이스가 롤백되었습니다.")
        sys.exit(1)

    finally:
        db.close()


if __name__ == "__main__":
    migrate_data()
