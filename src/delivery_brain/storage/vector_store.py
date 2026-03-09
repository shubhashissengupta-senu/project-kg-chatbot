"""
Vector Store for Delivery Brain

Uses ChromaDB (Apache-2.0 license) for vector embeddings storage.
"""

import os
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)


class DeliveryBrainVectorStore:
    """
    ChromaDB-based vector store for document embeddings.

    Uses ChromaDB's built-in ONNX embeddings by default,
    or can use custom embedding functions.
    """

    def __init__(self,
                 persist_directory: str = "./data/chroma_delivery_brain",
                 collection_name: str = "delivery_brain_docs",
                 embedding_function: str = "default"):
        """
        Initialize vector store.

        Args:
            persist_directory: Directory for ChromaDB persistence
            collection_name: Name of the collection
            embedding_function: Embedding function to use ("default" for ONNX)
        """
        self.persist_directory = persist_directory
        self.collection_name = collection_name
        self.embedding_function_type = embedding_function

        self._client = None
        self._collection = None
        self._embedding_function = None

        self._initialize_store()

    def _initialize_store(self):
        """Initialize ChromaDB"""
        try:
            import chromadb
            from chromadb.config import Settings

            # Ensure directory exists
            persist_path = Path(self.persist_directory)
            persist_path.mkdir(parents=True, exist_ok=True)

            # Initialize client with persistence
            self._client = chromadb.PersistentClient(
                path=str(persist_path),
                settings=Settings(
                    anonymized_telemetry=False,
                    allow_reset=True
                )
            )

            # Set up embedding function
            if self.embedding_function_type == "default":
                # Use ChromaDB's default ONNX embeddings
                from chromadb.utils import embedding_functions
                self._embedding_function = embedding_functions.DefaultEmbeddingFunction()
            elif self.embedding_function_type == "sentence_transformers":
                from chromadb.utils import embedding_functions
                self._embedding_function = embedding_functions.SentenceTransformerEmbeddingFunction(
                    model_name="all-MiniLM-L6-v2"
                )

            # Get or create collection
            self._collection = self._client.get_or_create_collection(
                name=self.collection_name,
                embedding_function=self._embedding_function,
                metadata={"description": "Delivery Brain document embeddings"}
            )

            logger.info(
                f"ChromaDB initialized: {self.collection_name} "
                f"({self._collection.count()} documents)"
            )

        except ImportError:
            logger.error("ChromaDB not available. Install with: pip install chromadb")
            raise

    def add_documents(self,
                      documents: List[str],
                      metadatas: List[Dict[str, Any]] = None,
                      ids: List[str] = None) -> int:
        """
        Add documents to the vector store.

        Args:
            documents: List of document texts
            metadatas: List of metadata dicts
            ids: List of document IDs

        Returns:
            Number of documents added
        """
        if not documents:
            return 0

        # Generate IDs if not provided
        if ids is None:
            import uuid
            ids = [str(uuid.uuid4()) for _ in documents]

        # Ensure metadatas is provided
        if metadatas is None:
            metadatas = [{} for _ in documents]

        # Add timestamp to metadata
        for meta in metadatas:
            meta["indexed_at"] = datetime.now().isoformat()

        # Add to collection
        self._collection.add(
            documents=documents,
            metadatas=metadatas,
            ids=ids
        )

        logger.debug(f"Added {len(documents)} documents to vector store")
        return len(documents)

    def add_chunks(self, chunks: List[Dict[str, Any]]) -> int:
        """
        Add chunks to vector store.

        Args:
            chunks: List of chunk dicts with 'content', 'chunk_id', and optional metadata

        Returns:
            Number of chunks added
        """
        if not chunks:
            return 0

        documents = []
        metadatas = []
        ids = []

        for chunk in chunks:
            documents.append(chunk.get("content", ""))
            ids.append(chunk.get("chunk_id", str(hash(chunk.get("content", "")))))

            # Build metadata
            meta = {
                "document_id": chunk.get("document_id", ""),
                "chunk_index": chunk.get("chunk_index", 0),
                "total_chunks": chunk.get("total_chunks", 1),
            }

            # Add any additional metadata
            if "metadata" in chunk:
                for k, v in chunk["metadata"].items():
                    # ChromaDB only supports str, int, float, bool
                    if isinstance(v, (str, int, float, bool)):
                        meta[k] = v
                    elif v is not None:
                        meta[k] = str(v)

            metadatas.append(meta)

        return self.add_documents(documents, metadatas, ids)

    def search(self,
               query: str,
               n_results: int = 10,
               where: Dict[str, Any] = None,
               include: List[str] = None) -> List[Dict[str, Any]]:
        """
        Search for similar documents.

        Args:
            query: Search query text
            n_results: Number of results to return
            where: Filter conditions
            include: What to include in results

        Returns:
            List of search results
        """
        if include is None:
            include = ["documents", "metadatas", "distances"]

        results = self._collection.query(
            query_texts=[query],
            n_results=n_results,
            where=where,
            include=include
        )

        # Format results
        formatted = []
        if results["ids"] and results["ids"][0]:
            for i, doc_id in enumerate(results["ids"][0]):
                result = {
                    "id": doc_id,
                    "distance": results["distances"][0][i] if "distances" in results else None,
                    "document": results["documents"][0][i] if "documents" in results else None,
                    "metadata": results["metadatas"][0][i] if "metadatas" in results else None,
                }
                formatted.append(result)

        return formatted

    def search_by_document_id(self, document_id: str) -> List[Dict[str, Any]]:
        """Get all chunks for a specific document"""
        results = self._collection.get(
            where={"document_id": document_id},
            include=["documents", "metadatas"]
        )

        formatted = []
        if results["ids"]:
            for i, chunk_id in enumerate(results["ids"]):
                formatted.append({
                    "id": chunk_id,
                    "document": results["documents"][i] if results["documents"] else None,
                    "metadata": results["metadatas"][i] if results["metadatas"] else None,
                })

        return formatted

    def delete_by_document_id(self, document_id: str) -> int:
        """Delete all chunks for a document"""
        # Get chunk IDs first
        results = self._collection.get(
            where={"document_id": document_id},
            include=[]
        )

        if results["ids"]:
            self._collection.delete(ids=results["ids"])
            logger.debug(f"Deleted {len(results['ids'])} chunks for document {document_id}")
            return len(results["ids"])

        return 0

    def delete_by_ids(self, ids: List[str]) -> int:
        """Delete documents by IDs"""
        if ids:
            self._collection.delete(ids=ids)
            return len(ids)
        return 0

    def get_statistics(self) -> Dict[str, Any]:
        """Get vector store statistics"""
        return {
            "collection_name": self.collection_name,
            "persist_directory": self.persist_directory,
            "document_count": self._collection.count(),
            "embedding_function": self.embedding_function_type,
        }

    def clear_collection(self):
        """Clear all documents from collection"""
        # Delete and recreate collection
        self._client.delete_collection(self.collection_name)
        self._collection = self._client.create_collection(
            name=self.collection_name,
            embedding_function=self._embedding_function,
            metadata={"description": "Delivery Brain document embeddings"}
        )
        logger.info(f"Cleared collection: {self.collection_name}")

    def get_all_document_ids(self) -> List[str]:
        """Get all unique document IDs"""
        results = self._collection.get(include=["metadatas"])

        doc_ids = set()
        if results["metadatas"]:
            for meta in results["metadatas"]:
                if meta and "document_id" in meta:
                    doc_ids.add(meta["document_id"])

        return list(doc_ids)


def create_vector_store(persist_directory: str = None,
                        collection_name: str = None) -> DeliveryBrainVectorStore:
    """Factory function to create vector store"""
    kwargs = {}
    if persist_directory:
        kwargs["persist_directory"] = persist_directory
    if collection_name:
        kwargs["collection_name"] = collection_name

    return DeliveryBrainVectorStore(**kwargs)
