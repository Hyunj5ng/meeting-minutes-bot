"""
데이터베이스 초기화 스크립트
"""
from database import engine, Base
from models import TranscriptRecord, SummaryRecord

def init_database():
    """데이터베이스 테이블 생성"""
    print("데이터베이스 테이블을 생성합니다...")
    Base.metadata.create_all(bind=engine)
    print("✅ 데이터베이스 테이블 생성 완료!")
    print("   - transcript_records (STT 변환 레코드)")
    print("   - summary_records (GPT 요약 레코드)")

if __name__ == "__main__":
    init_database()
