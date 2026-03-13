"""
기존 요약 레코드를 일괄 임베딩하는 스크립트.
멱등성 보장: upsert로 중복 실행 안전.

사용법:
    python backfill_embeddings.py
"""
import asyncio
from database import SessionLocal
from models import SummaryRecord, TranscriptRecord
from rag_service import RAGService


async def backfill():
    db = SessionLocal()
    rag = RAGService()

    try:
        records = (
            db.query(SummaryRecord)
            .join(TranscriptRecord)
            .filter(TranscriptRecord.user_id.isnot(None))
            .all()
        )

        print(f"임베딩 대상: {len(records)}개 요약 레코드")

        for i, record in enumerate(records, 1):
            user_id = record.transcript.user_id
            metadata = {}
            if record.transcript.meeting_title:
                metadata["meeting_title"] = record.transcript.meeting_title
            if record.transcript.project_name:
                metadata["project_name"] = record.transcript.project_name

            await rag.embed_and_store(
                user_id=user_id,
                summary_id=record.id,
                summary_text=record.summary,
                metadata=metadata,
            )
            print(f"  [{i}/{len(records)}] summary_id={record.id}, user_id={user_id}")

        print("백필 완료!")
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(backfill())
