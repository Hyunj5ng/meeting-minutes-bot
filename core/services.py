"""
외부 API 클라이언트 싱글톤 (STT / LLM / RAG).

서버 시작 시 init_services()로 초기화하고, 라우터에서는
`from core import services` 후 `services.stt_processor` 형태로 접근한다
(모듈 속성 접근이어야 초기화 이후의 값을 본다).
"""
from stt_module import STTProcessor
from gpt_summarizer import GPTSummarizer
from rag_service import RAGService

stt_processor: STTProcessor | None = None
gpt_summarizer: GPTSummarizer | None = None
rag_service: RAGService | None = None


def init_services():
    global stt_processor, gpt_summarizer, rag_service
    print("모델 초기화 중...")
    stt_processor = STTProcessor()
    gpt_summarizer = GPTSummarizer()
    rag_service = RAGService()
    print("모델 초기화 완료!")


async def backfill_embeddings():
    """서버 시작 시 미임베딩 요약을 백그라운드로 백필"""
    from database import get_db
    from models import TranscriptRecord, SummaryRecord

    try:
        if not rag_service or not rag_service.openai_client:
            print("RAG 백필 스킵: OpenAI 클라이언트 미설정")
            return

        db = next(get_db())
        try:
            records = db.query(SummaryRecord).join(TranscriptRecord).filter(
                TranscriptRecord.user_id.isnot(None)
            ).all()

            if not records:
                return

            print(f"RAG 백필 시작: {len(records)}개 요약")
            for i, record in enumerate(records, 1):
                user_id = record.transcript.user_id
                collection = rag_service._get_collection(user_id)
                doc_id = f"summary_{record.id}"
                # 이미 임베딩된 건 스킵
                existing = collection.get(ids=[doc_id])
                if existing and existing["ids"]:
                    continue

                metadata = {"summary_id": record.id, "user_id": user_id}
                if record.transcript.meeting_title:
                    metadata["meeting_title"] = record.transcript.meeting_title
                if record.transcript.project_name:
                    metadata["project_name"] = record.transcript.project_name

                await rag_service.embed_and_store(
                    user_id=user_id,
                    summary_id=record.id,
                    summary_text=record.summary,
                    metadata=metadata,
                )
                print(f"  RAG 백필 [{i}/{len(records)}] summary_id={record.id}")
            print("RAG 백필 완료!")
        finally:
            db.close()
    except Exception as e:
        print(f"RAG 백필 실패 (무시): {e}")
