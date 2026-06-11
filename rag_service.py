"""
RAG 서비스 — 사용자별 과거 회의록 맥락 검색
ChromaDB (파일 기반) + OpenAI text-embedding-3-small
"""
import os
import chromadb
from openai import AsyncOpenAI
from typing import Optional

# 임베딩 모델 설정
EMBEDDING_MODEL = "text-embedding-3-small"
MAX_CONTEXT_RESULTS = 3
MAX_SUMMARY_LENGTH = 2000  # 각 요약 truncate 길이 (토큰 제한 고려)

# ChromaDB 저장 경로
CHROMA_DATA_DIR = os.getenv("CHROMA_DATA_DIR", "chroma_data")


class RAGService:
    def __init__(self):
        self.openai_client: Optional[AsyncOpenAI] = None
        self.chroma_client: Optional[chromadb.PersistentClient] = None

        openai_api_key = os.getenv("OPENAI_API_KEY")
        if openai_api_key:
            self.openai_client = AsyncOpenAI(api_key=openai_api_key)
        else:
            print("경고: OPENAI_API_KEY 미설정 — RAG 임베딩 비활성화")

        os.makedirs(CHROMA_DATA_DIR, exist_ok=True)
        self.chroma_client = chromadb.PersistentClient(path=CHROMA_DATA_DIR)
        print(f"ChromaDB 초기화 완료 (저장 경로: {CHROMA_DATA_DIR})")

    def _get_collection(self, user_id: int):
        """사용자별 ChromaDB 컬렉션 반환 (없으면 생성)"""
        collection_name = f"user_{user_id}_summaries"
        return self.chroma_client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    async def _get_embedding(self, text: str) -> list[float]:
        """OpenAI 임베딩 벡터 생성"""
        if not self.openai_client:
            raise ValueError("OPENAI_API_KEY가 설정되지 않았습니다")

        response = await self.openai_client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=text[:8000],  # 모델 입력 한계 고려
        )
        return response.data[0].embedding

    async def embed_and_store(
        self,
        user_id: int,
        summary_id: int,
        summary_text: str,
        metadata: Optional[dict] = None,
    ):
        """요약을 임베딩하여 ChromaDB에 저장"""
        if not self.openai_client:
            return

        try:
            embedding = await self._get_embedding(summary_text)
            collection = self._get_collection(user_id)

            doc_id = f"summary_{summary_id}"
            doc_metadata = {"summary_id": summary_id, "user_id": user_id}
            if metadata:
                doc_metadata.update(metadata)

            collection.upsert(
                ids=[doc_id],
                embeddings=[embedding],
                documents=[summary_text[:MAX_SUMMARY_LENGTH]],
                metadatas=[doc_metadata],
            )
            print(f"RAG 저장 완료: user={user_id}, summary={summary_id}")
        except Exception as e:
            print(f"RAG 저장 실패: {e}")

    async def retrieve_context(
        self,
        user_id: int,
        query_text: str,
        n_results: int = MAX_CONTEXT_RESULTS,
        project_name: Optional[str] = None,
    ) -> list[str]:
        """관련 과거 요약을 검색하여 반환.

        project_name이 주어지면 같은 프로젝트의 회의록을 우선 검색하고,
        모자라면 전체에서 보충한다 (같은 프로젝트 회의가 맥락상 가장 관련 깊음)."""
        if not self.openai_client:
            return []

        try:
            collection = self._get_collection(user_id)
            if collection.count() == 0:
                return []

            query_embedding = await self._get_embedding(query_text)
            max_n = min(n_results, collection.count())

            seen_ids: set[str] = set()
            documents: list[str] = []

            def _collect(results):
                ids = results.get("ids", [[]])[0]
                docs = results.get("documents", [[]])[0]
                for doc_id, doc in zip(ids, docs):
                    if doc and doc_id not in seen_ids and len(documents) < n_results:
                        seen_ids.add(doc_id)
                        documents.append(doc[:MAX_SUMMARY_LENGTH])

            # 1차: 같은 프로젝트 우선
            if project_name:
                try:
                    project_results = collection.query(
                        query_embeddings=[query_embedding],
                        n_results=max_n,
                        where={"project_name": project_name},
                    )
                    _collect(project_results)
                except Exception as e:
                    print(f"RAG 프로젝트 필터 검색 실패 (전체 검색으로 진행): {e}")

            # 2차: 전체에서 보충
            if len(documents) < n_results:
                results = collection.query(
                    query_embeddings=[query_embedding],
                    n_results=max_n,
                )
                _collect(results)

            return documents
        except Exception as e:
            print(f"RAG 검색 실패: {e}")
            return []

    def delete_summary(self, user_id: int, summary_id: int):
        """요약 삭제 시 임베딩도 제거 (회의록 삭제와 동기화)"""
        try:
            collection = self._get_collection(user_id)
            collection.delete(ids=[f"summary_{summary_id}"])
            print(f"RAG 삭제 완료: user={user_id}, summary={summary_id}")
        except Exception as e:
            print(f"RAG 삭제 실패 (무시): {e}")
