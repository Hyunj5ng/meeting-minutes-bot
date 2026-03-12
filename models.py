"""
데이터베이스 모델 정의
"""
from sqlalchemy import Column, Index, Integer, String, Float, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base


class User(Base):
    """사용자 테이블 (Google OAuth)"""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)

    # Google OAuth 정보
    google_id = Column(String(255), unique=True, nullable=False, index=True, comment="Google sub ID")
    email = Column(String(500), nullable=False, unique=True, comment="Google 이메일")
    name = Column(String(500), nullable=True, comment="표시 이름")
    picture = Column(String(1000), nullable=True, comment="프로필 이미지 URL")

    # 타임스탬프
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="가입 시각")
    last_login_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), comment="마지막 로그인")

    # 관계
    transcripts = relationship("TranscriptRecord", back_populates="user", cascade="all, delete-orphan")
    usage_records = relationship("UsageRecord", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User(id={self.id}, email='{self.email}')>"


class TranscriptRecord(Base):
    """STT 변환 레코드 테이블 (음원 → 텍스트)"""
    __tablename__ = "transcript_records"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)

    # 사용자 (nullable=True: 기존 데이터 호환)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True, comment="소유자 ID")

    # 파일 정보
    filename = Column(String(500), nullable=False, comment="원본 파일명")
    file_size = Column(Integer, nullable=False, comment="파일 크기 (bytes)")
    audio_duration = Column(Float, nullable=True, comment="오디오 길이 (초)")

    # STT 결과
    transcript = Column(Text, nullable=False, comment="STT 변환 결과")

    # 모델 정보
    whisper_model = Column(String(50), nullable=False, default="base", comment="사용한 Whisper 모델")

    # 회의 맥락 정보
    project_name = Column(String(500), nullable=True, comment="프로젝트명")
    meeting_title = Column(String(500), nullable=True, comment="회의 제목")
    attendees = Column(Text, nullable=True, comment="참석자 목록")
    keywords = Column(Text, nullable=True, comment="관련 키워드")

    # 처리 시간
    stt_processing_time = Column(Float, nullable=True, comment="STT 처리 시간 (초)")

    # 비용 (USD)
    stt_cost = Column(Float, nullable=True, comment="STT API 비용 (USD)")

    # 타임스탬프
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="생성 시각")

    # 관계
    user = relationship("User", back_populates="transcripts")
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

    # 토큰 사용량
    input_tokens = Column(Integer, nullable=True, comment="입력 토큰 수")
    output_tokens = Column(Integer, nullable=True, comment="출력 토큰 수")

    # 비용 (USD)
    llm_cost = Column(Float, nullable=True, comment="LLM API 비용 (USD)")

    # 타임스탬프
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="생성 시각")

    # 관계 (N:1 - 여러 summary가 하나의 transcript에 속함)
    transcript = relationship("TranscriptRecord", back_populates="summaries")

    def __repr__(self):
        return f"<SummaryRecord(id={self.id}, transcript_id={self.transcript_id}, gpt_model='{self.gpt_model}', created_at={self.created_at})>"


class UsageRecord(Base):
    """사용량 추적 테이블"""
    __tablename__ = "usage_records"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)

    # 사용자
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True, comment="사용자 ID")

    # 사용 정보
    action_type = Column(String(20), nullable=False, comment="stt 또는 summarize")
    duration_minutes = Column(Float, nullable=True, default=0.0, comment="오디오 길이 (분, STT 전용)")
    cost = Column(Float, nullable=True, default=0.0, comment="API 비용 (USD)")

    # 타임스탬프
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="사용 시각")

    # 관계
    user = relationship("User", back_populates="usage_records")

    # 복합 인덱스 (사용량 조회 최적화)
    __table_args__ = (
        Index("ix_usage_user_action_date", "user_id", "action_type", "created_at"),
    )

    def __repr__(self):
        return f"<UsageRecord(id={self.id}, user_id={self.user_id}, action='{self.action_type}')>"
