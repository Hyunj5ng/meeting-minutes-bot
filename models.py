"""
데이터베이스 모델 정의
"""
from sqlalchemy import Column, Integer, String, Float, Text, DateTime
from sqlalchemy.sql import func
from database import Base


class MeetingRecord(Base):
    """회의록 레코드 테이블"""
    __tablename__ = "meeting_records"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)

    # 파일 정보
    filename = Column(String(500), nullable=False, comment="원본 파일명")
    file_size = Column(Integer, nullable=False, comment="파일 크기 (bytes)")
    audio_duration = Column(Float, nullable=True, comment="오디오 길이 (초)")

    # STT 결과
    transcript = Column(Text, nullable=False, comment="STT 변환 결과")

    # 회의록 (GPT 요약)
    summary = Column(Text, nullable=True, comment="GPT 회의록")

    # 모델 정보
    whisper_model = Column(String(50), nullable=False, default="base", comment="사용한 Whisper 모델")
    gpt_model = Column(String(50), nullable=True, comment="사용한 GPT 모델")

    # 처리 시간
    stt_processing_time = Column(Float, nullable=True, comment="STT 처리 시간 (초)")
    gpt_processing_time = Column(Float, nullable=True, comment="GPT 처리 시간 (초)")

    # 타임스탬프
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="생성 시각")
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), comment="수정 시각")

    def __repr__(self):
        return f"<MeetingRecord(id={self.id}, filename='{self.filename}', created_at={self.created_at})>"
