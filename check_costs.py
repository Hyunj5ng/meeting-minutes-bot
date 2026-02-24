"""
비용 확인 스크립트
사용법: DATABASE_URL="postgresql://..." python check_costs.py
"""
import os
import sys
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./meeting_minutes.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)


def show_costs():
    with engine.connect() as conn:
        # 최근 레코드별 비용
        rows = conn.execute(text("""
            SELECT t.id, t.filename, t.audio_duration, t.stt_cost,
                   s.gpt_model, s.input_tokens, s.output_tokens, s.llm_cost,
                   COALESCE(t.stt_cost, 0) + COALESCE(s.llm_cost, 0) AS total_cost,
                   t.created_at
            FROM transcript_records t
            LEFT JOIN summary_records s ON t.id = s.transcript_id
            ORDER BY t.created_at DESC
            LIMIT 20
        """)).fetchall()

        print("=" * 90)
        print("  최근 비용 내역 (최신 20건)")
        print("=" * 90)
        print(f"{'ID':>4}  {'파일명':<25}  {'시간(분)':>8}  {'STT($)':>8}  {'LLM($)':>8}  {'합계($)':>8}  {'모델':<15}")
        print("-" * 90)

        for r in rows:
            duration_min = f"{r.audio_duration / 60:.1f}" if r.audio_duration else "-"
            stt = f"{r.stt_cost:.4f}" if r.stt_cost else "-"
            llm = f"{r.llm_cost:.4f}" if r.llm_cost else "-"
            total = f"{r.total_cost:.4f}" if r.total_cost else "-"
            model = r.gpt_model or "-"
            fname = r.filename[:25] if r.filename else "-"
            print(f"{r.id:>4}  {fname:<25}  {duration_min:>8}  {stt:>8}  {llm:>8}  {total:>8}  {model:<15}")

        # 전체 요약
        summary = conn.execute(text("""
            SELECT
                COUNT(DISTINCT t.id) AS total_records,
                COALESCE(SUM(t.stt_cost), 0) AS total_stt,
                COALESCE(SUM(s.llm_cost), 0) AS total_llm,
                COALESCE(SUM(t.stt_cost), 0) + COALESCE(SUM(s.llm_cost), 0) AS total_cost
            FROM transcript_records t
            LEFT JOIN summary_records s ON t.id = s.transcript_id
        """)).fetchone()

        print("\n" + "=" * 90)
        print("  전체 비용 요약")
        print("=" * 90)
        print(f"  총 레코드:  {summary.total_records}건")
        print(f"  STT 비용:   ${summary.total_stt:.4f}")
        print(f"  LLM 비용:   ${summary.total_llm:.4f}")
        print(f"  총 비용:    ${summary.total_cost:.4f}")

        if summary.total_records > 0:
            avg = summary.total_cost / summary.total_records
            print(f"  건당 평균:  ${avg:.4f}")

        print("=" * 90)

        # Groq 전환 전후 비교 (분당 STT 비용으로 구분: >$0.003이면 OpenAI)
        comparison = conn.execute(text("""
            SELECT
                CASE WHEN t.stt_cost / (t.audio_duration / 60) > 0.003
                     THEN 'OpenAI' ELSE 'Groq' END AS provider,
                COUNT(DISTINCT t.id) AS cnt,
                SUM(t.audio_duration) / 60 AS total_minutes,
                SUM(t.stt_cost) AS total_stt,
                SUM(s.llm_cost) AS total_llm,
                SUM(t.stt_cost) + SUM(s.llm_cost) AS total_cost,
                AVG(t.stt_cost + COALESCE(s.llm_cost, 0)) AS avg_per_record,
                (SUM(t.stt_cost) + SUM(s.llm_cost)) / (SUM(t.audio_duration) / 60) AS cost_per_min
            FROM transcript_records t
            LEFT JOIN summary_records s ON t.id = s.transcript_id
            WHERE t.stt_cost IS NOT NULL AND t.audio_duration > 0
            GROUP BY provider
            ORDER BY provider
        """)).fetchall()

        if len(comparison) > 1:
            print(f"\n{'=' * 90}")
            print("  Groq 전환 전후 비용 비교")
            print(f"{'=' * 90}")
            print(f"  {'':>10}  {'건수':>6}  {'총 시간(분)':>11}  {'STT($)':>8}  {'LLM($)':>8}  {'합계($)':>8}  {'건당평균($)':>11}  {'분당비용($)':>11}")
            print(f"  {'-' * 82}")

            rows_map = {r.provider: r for r in comparison}
            for provider in ["OpenAI", "Groq"]:
                r = rows_map.get(provider)
                if r:
                    print(f"  {provider:>10}  {r.cnt:>6}  {r.total_minutes:>11.1f}  {r.total_stt:>8.4f}  {r.total_llm:>8.4f}  {r.total_cost:>8.4f}  {r.avg_per_record:>11.4f}  {r.cost_per_min:>11.6f}")

            openai = rows_map.get("OpenAI")
            groq = rows_map.get("Groq")
            if openai and groq:
                stt_save = (1 - groq.cost_per_min / openai.cost_per_min) * 100
                print(f"\n  => 분당 비용 절감률: {stt_save:.1f}%")

            print(f"{'=' * 90}")


if __name__ == "__main__":
    show_costs()
