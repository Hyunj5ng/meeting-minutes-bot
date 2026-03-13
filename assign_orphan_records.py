"""
기존 미팅 로그(user_id IS NULL)를 특정 사용자에게 할당하는 스크립트.
멱등성 보장: 재실행해도 안전합니다.

사용법:
    python assign_orphan_records.py
"""
from database import SessionLocal
from models import User, TranscriptRecord

TARGET_EMAIL = "hyunjong.kim@coxwave.com"


def assign_orphan_records():
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == TARGET_EMAIL).first()
        if not user:
            print(f"사용자를 찾을 수 없습니다: {TARGET_EMAIL}")
            return

        updated = (
            db.query(TranscriptRecord)
            .filter(TranscriptRecord.user_id.is_(None))
            .update({"user_id": user.id}, synchronize_session="fetch")
        )
        db.commit()

        remaining = (
            db.query(TranscriptRecord)
            .filter(TranscriptRecord.user_id.is_(None))
            .count()
        )

        print(f"완료: {updated}개 레코드를 {TARGET_EMAIL} (id={user.id})에 할당했습니다.")
        print(f"남은 orphan 레코드: {remaining}개")
    finally:
        db.close()


if __name__ == "__main__":
    assign_orphan_records()
