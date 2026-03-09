"""
Vector Store using ChromaDB
Provides semantic search capabilities for RAG.
"""

import os
import logging
from pathlib import Path
from typing import List, Dict, Optional, Any
from dataclasses import dataclass

from .document_store import DocumentStore, DocumentChunk

logger = logging.getLogger(__name__)


@dataclass
class VectorSearchResult:
    """Result from vector search"""
    chunk: DocumentChunk
    score: float
    distance: float


class ChromaVectorStore:
    """
    ChromaDB-based vector store for semantic search.
    Uses ChromaDB's default ONNX-based embeddings (no PyTorch required).
    """

    def __init__(
        self,
        document_store: DocumentStore,
        persist_directory: str = None,
        embedding_model: str = None,
        collection_name: str = "project_docs"
    ):
        self.document_store = document_store
        self.persist_directory = persist_directory or os.getenv(
            "CHROMA_PERSIST_DIR", "./data/chroma_db"
        )
        self.embedding_model_name = embedding_model or os.getenv(
            "EMBEDDING_MODEL", "all-MiniLM-L6-v2"
        )
        self.collection_name = collection_name

        self.client = None
        self.collection = None
        self.embedding_function = None
        self.is_initialized = False

        self._initialize()

    def _initialize(self):
        """Initialize ChromaDB client and embedding function"""
        try:
            import chromadb
            from chromadb.utils import embedding_functions

            # Create persist directory
            persist_path = Path(self.persist_directory)
            persist_path.mkdir(parents=True, exist_ok=True)

            # Initialize ChromaDB client with persistence
            self.client = chromadb.PersistentClient(path=str(persist_path))

            # Initialize embedding function - use default ONNX-based embeddings
            # This avoids PyTorch dependency and works well for document search
            self.embedding_function = embedding_functions.DefaultEmbeddingFunction()

            # Get or create collection
            self.collection = self.client.get_or_create_collection(
                name=self.collection_name,
                embedding_function=self.embedding_function,
                metadata={"hnsw:space": "cosine"}
            )

            self.is_initialized = True
            logger.info(f"ChromaDB initialized with default ONNX embeddings")
            logger.info(f"Collection '{self.collection_name}' has {self.collection.count()} documents")

        except ImportError as e:
            logger.error(f"ChromaDB not installed: {e}")
            logger.error("Run: pip install chromadb")
        except Exception as e:
            logger.error(f"Failed to initialize ChromaDB: {e}")

    def index_documents(self, force_reindex: bool = False) -> int:
        """Index all documents from the document store"""
        if not self.is_initialized:
            logger.error("ChromaDB not initialized")
            return 0

        chunks = self.document_store.get_all_chunks()
        if not chunks:
            logger.warning("No chunks to index")
            return 0

        # Check if already indexed
        existing_count = self.collection.count()
        if existing_count > 0 and not force_reindex:
            logger.info(f"Collection already has {existing_count} documents. Skipping indexing.")
            return existing_count

        # Clear existing if force reindex
        if force_reindex and existing_count > 0:
            logger.info("Force reindex: clearing existing collection")
            self.client.delete_collection(self.collection_name)
            self.collection = self.client.create_collection(
                name=self.collection_name,
                embedding_function=self.embedding_function,
                metadata={"hnsw:space": "cosine"}
            )

        # Prepare data for indexing
        ids = []
        documents = []
        metadatas = []

        for chunk in chunks:
            ids.append(chunk.chunk_id)
            documents.append(chunk.content)
            metadatas.append({
                "source_file": chunk.source_file,
                "source_title": chunk.source_title,
                "chunk_index": chunk.chunk_index,
                "document_type": chunk.metadata.get("document_type", "General"),
                "section": chunk.metadata.get("section", ""),
                "date_str": chunk.metadata.get("date_str", ""),
            })

        # Index in batches
        batch_size = 100
        total_indexed = 0

        for i in range(0, len(ids), batch_size):
            batch_ids = ids[i:i + batch_size]
            batch_docs = documents[i:i + batch_size]
            batch_meta = metadatas[i:i + batch_size]

            try:
                self.collection.add(
                    ids=batch_ids,
                    documents=batch_docs,
                    metadatas=batch_meta
                )
                total_indexed += len(batch_ids)
            except Exception as e:
                logger.error(f"Error indexing batch {i}: {e}")

        logger.info(f"Indexed {total_indexed} document chunks")
        return total_indexed

    def search(
        self,
        query: str,
        top_k: int = 5,
        filter_doc_types: List[str] = None
    ) -> List[VectorSearchResult]:
        """
        Semantic search for relevant chunks.

        Args:
            query: Search query
            top_k: Number of results to return
            filter_doc_types: Optional list of document types to filter by (RBAC)

        Returns:
            List of VectorSearchResult
        """
        if not self.is_initialized or self.collection.count() == 0:
            logger.warning("Vector store not initialized or empty")
            return []

        # Build where clause for filtering
        where_clause = None
        if filter_doc_types:
            where_clause = {"document_type": {"$in": filter_doc_types}}

        try:
            results = self.collection.query(
                query_texts=[query],
                n_results=top_k,
                where=where_clause,
                include=["documents", "metadatas", "distances"]
            )

            search_results = []
            if results and results["ids"] and results["ids"][0]:
                for i, chunk_id in enumerate(results["ids"][0]):
                    # Get the original chunk from document store
                    chunk = self.document_store.get_chunk_by_id(chunk_id)
                    if chunk:
                        distance = results["distances"][0][i] if results["distances"] else 0
                        # Convert distance to similarity score (cosine distance to similarity)
                        score = 1 - distance

                        search_results.append(VectorSearchResult(
                            chunk=chunk,
                            score=score,
                            distance=distance
                        ))

            return search_results

        except Exception as e:
            logger.error(f"Vector search failed: {e}")
            return []

    def hybrid_search(
        self,
        query: str,
        tfidf_results: List[Any],
        top_k: int = 5,
        vector_weight: float = 0.7
    ) -> List[VectorSearchResult]:
        """
        Combine vector search with TF-IDF results for hybrid retrieval.

        Args:
            query: Search query
            tfidf_results: Results from TF-IDF retriever
            top_k: Number of results
            vector_weight: Weight for vector scores (0-1)

        Returns:
            Combined and reranked results
        """
        vector_results = self.search(query, top_k=top_k * 2)

        # Create score maps
        vector_scores = {r.chunk.chunk_id: r.score for r in vector_results}
        tfidf_scores = {}
        tfidf_chunks = {}

        for r in tfidf_results:
            chunk_id = r.chunk.chunk_id
            tfidf_scores[chunk_id] = r.score
            tfidf_chunks[chunk_id] = r.chunk

        # Combine all chunk IDs
        all_chunk_ids = set(vector_scores.keys()) | set(tfidf_scores.keys())

        # Calculate hybrid scores
        combined_results = []
        tfidf_weight = 1 - vector_weight

        for chunk_id in all_chunk_ids:
            v_score = vector_scores.get(chunk_id, 0)
            t_score = tfidf_scores.get(chunk_id, 0)

            # Normalize TF-IDF scores (they tend to be smaller)
            t_score_normalized = min(1.0, t_score * 5)

            hybrid_score = (vector_weight * v_score) + (tfidf_weight * t_score_normalized)

            # Get chunk from either source
            chunk = None
            for r in vector_results:
                if r.chunk.chunk_id == chunk_id:
                    chunk = r.chunk
                    break
            if not chunk:
                chunk = tfidf_chunks.get(chunk_id)

            if chunk:
                combined_results.append(VectorSearchResult(
                    chunk=chunk,
                    score=hybrid_score,
                    distance=1 - hybrid_score
                ))

        # Sort by hybrid score
        combined_results.sort(key=lambda x: x.score, reverse=True)
        return combined_results[:top_k]

    def get_stats(self) -> Dict:
        """Get vector store statistics"""
        if not self.is_initialized:
            return {"initialized": False}

        return {
            "initialized": True,
            "collection_name": self.collection_name,
            "document_count": self.collection.count(),
            "embedding_model": "default-onnx (all-MiniLM-L6-v2)",
            "persist_directory": self.persist_directory
        }
