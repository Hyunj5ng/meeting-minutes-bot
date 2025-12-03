"""
데이터베이스 모델 정의
"""
from sqlalchemy import Column, Integer, String, Float, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base


class TranscriptRecord(Base):
    """STT 변환 레코드 테이블 (음원 → 텍스트)"""
    __tablename__ = "transcript_records"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)

    # 파일 정보
    filename = Column(String(500), nullable=False, comment="원본 파일명")
    file_size = Column(Integer, nullable=False, comment="파일 크기 (bytes)")
    audio_duration = Column(Float, nullable=True, comment="오디오 길이 (초)")

    # STT 결과
    transcript = Column(Text, nullable=False, comment="STT 변환 결과")

    # 모델 정보
    whisper_model = Column(String(50), nullable=False, default="base", comment="사용한 Whisper 모델")

    # 처리 시간
    stt_processing_time = Column(Float, nullable=True, comment="STT 처리 시간 (초)")

    # 타임스탬프
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="생성 시각")

    # 관계 (1:N - 하나의 transcript에 여러 summary)
    summaries = relationship("SummaryRecord", back_populates="transcript", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<TranscriptRecord(id={self.id}, filename='{self.filename}', created_at={self.created_at})>"


class SummaryRecord(Base):
    """GPT 요약 레코드 테이블 (텍스트 → 요약)"""
    __tablename__ = "summary_records"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)

    # 외래키
    transcript_id = Column(Integer, ForeignKey("transcript_records.id", ondelete="CASCADE"), nullable=False, comment="STT 레코드 ID")

    # GPT 요약 결과
    summary = Column(Text, nullable=False, comment="GPT 회의록")

    # 모델 정보
    gpt_model = Column(String(50), nullable=False, comment="사용한 GPT 모델")

    # 처리 시간
    gpt_processing_time = Column(Float, nullable=True, comment="GPT 처리 시간 (초)")

    # 타임스탬프
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="생성 시각")

    # 관계 (N:1 - 여러 summary가 하나의 transcript에 속함)
    transcript = relationship("TranscriptRecord", back_populates="summaries")

    def __repr__(self):
        return f"<SummaryRecord(id={self.id}, transcript_id={self.transcript_id}, gpt_model='{self.gpt_model}', created_at={self.created_at})>"
