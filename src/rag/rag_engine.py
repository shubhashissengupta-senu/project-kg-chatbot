"""
RAG Engine
Combines retrieval with LLM-powered response generation.
Supports hybrid retrieval using ChromaDB vectors and TF-IDF.
"""

from typing import List, Dict, Optional, TYPE_CHECKING
from dataclasses import dataclass
from pathlib import Path
import logging
import os

from .document_store import DocumentStore
from .retriever import DocumentRetriever, RetrievalResult
from .vector_store import ChromaVectorStore, VectorSearchResult

if TYPE_CHECKING:
    from ..llm.llm_service import LLMService

logger = logging.getLogger(__name__)


@dataclass
class RAGResponse:
    """Response from RAG engine"""
    answer: str
    sources: List[Dict]
    confidence: float
    query: str


class RAGEngine:
    """
    RAG Engine for answering ad-hoc questions.
    Uses hybrid retrieval (ChromaDB vectors + TF-IDF) with LLM-powered response generation.
    Falls back to TF-IDF only and template-based responses when components unavailable.
    """

    def __init__(
        self,
        data_directory: Optional[Path] = None,
        llm_service: "LLMService" = None,
        use_vector_store: bool = True
    ):
        self.store = DocumentStore(chunk_size=600, chunk_overlap=100)
        self.retriever: Optional[DocumentRetriever] = None
        self.vector_store: Optional[ChromaVectorStore] = None
        self.llm = llm_service
        self.is_initialized = False
        self.use_vector_store = use_vector_store

        if data_directory:
            self.initialize(data_directory)

    def initialize(self, data_directory: Path) -> int:
        """Initialize the RAG engine with documents"""
        data_directory = Path(data_directory)

        # Load documents into document store
        doc_count = self.store.load_directory(data_directory)
        chunk_count = len(self.store.get_all_chunks())

        # Initialize TF-IDF retriever
        self.retriever = DocumentRetriever(self.store)

        # Initialize vector store if enabled
        if self.use_vector_store:
            try:
                self.vector_store = ChromaVectorStore(self.store)
                if self.vector_store.is_initialized:
                    indexed = self.vector_store.index_documents()
                    logger.info(f"Vector store indexed {indexed} chunks")
                else:
                    logger.warning("Vector store initialization failed, using TF-IDF only")
                    self.vector_store = None
            except Exception as e:
                logger.warning(f"Failed to initialize vector store: {e}")
                self.vector_store = None

        self.is_initialized = True
        return chunk_count

    def set_llm_service(self, llm_service: "LLMService"):
        """Set or update the LLM service"""
        self.llm = llm_service
        logger.info(f"LLM service configured: {llm_service.is_available()}")

    def query(
        self,
        question: str,
        top_k: int = 5,
        allowed_doc_types: List[str] = None,
        use_hybrid: bool = True
    ) -> RAGResponse:
        """
        Answer a question using RAG.

        Args:
            question: User's question
            top_k: Number of chunks to retrieve
            allowed_doc_types: List of document types user can access (for RBAC)
            use_hybrid: Whether to use hybrid retrieval (vector + TF-IDF)

        Returns:
            RAGResponse with answer and sources
        """
        if not self.is_initialized or not self.retriever:
            return RAGResponse(
                answer="RAG engine not initialized. Please load documents first.",
                sources=[],
                confidence=0.0,
                query=question
            )

        # Retrieve relevant chunks using hybrid or TF-IDF only
        if use_hybrid and self.vector_store and self.vector_store.is_initialized:
            results = self._hybrid_retrieve(question, top_k, allowed_doc_types)
        else:
            results = self._tfidf_retrieve(question, top_k, allowed_doc_types)

        if not results:
            return RAGResponse(
                answer="I couldn't find relevant information to answer your question.",
                sources=[],
                confidence=0.0,
                query=question
            )

        # Generate response from retrieved chunks
        answer = self._generate_response(question, results)
        sources = self._format_sources(results)
        confidence = self._calculate_confidence(results)

        return RAGResponse(
            answer=answer,
            sources=sources,
            confidence=confidence,
            query=question
        )

    def _hybrid_retrieve(
        self,
        question: str,
        top_k: int,
        allowed_doc_types: List[str] = None
    ) -> List[RetrievalResult]:
        """Hybrid retrieval combining vector search and TF-IDF"""

        # Get TF-IDF results
        tfidf_results = self.retriever.retrieve(question, top_k=top_k * 2)

        # Apply RBAC filtering to TF-IDF results
        if allowed_doc_types:
            tfidf_results = [
                r for r in tfidf_results
                if r.chunk.metadata.get('document_type', 'General') in allowed_doc_types
            ]

        # Get vector search results with RBAC filtering
        vector_results = self.vector_store.search(
            question,
            top_k=top_k * 2,
            filter_doc_types=allowed_doc_types
        )

        # Combine using hybrid search
        hybrid_results = self.vector_store.hybrid_search(
            question,
            tfidf_results,
            top_k=top_k,
            vector_weight=0.6  # Slightly favor semantic similarity
        )

        # Convert VectorSearchResult to RetrievalResult format
        results = []
        for vr in hybrid_results:
            results.append(RetrievalResult(
                chunk=vr.chunk,
                score=vr.score,
                match_terms=[]  # Hybrid doesn't track match terms
            ))

        return results

    def _tfidf_retrieve(
        self,
        question: str,
        top_k: int,
        allowed_doc_types: List[str] = None
    ) -> List[RetrievalResult]:
        """TF-IDF only retrieval (fallback)"""
        results = self.retriever.retrieve(question, top_k=top_k * 2)

        # Apply RBAC filtering
        if allowed_doc_types:
            results = [
                r for r in results
                if r.chunk.metadata.get('document_type', 'General') in allowed_doc_types
            ]

        return results[:top_k]

    def _generate_response(self, question: str, results: List[RetrievalResult]) -> str:
        """Generate a response from retrieved chunks using LLM or fallback to templates"""

        # Build context from retrieved chunks
        context_parts = []
        seen_content = set()

        for result in results[:5]:
            content = result.chunk.content.strip()
            content_key = content[:100]
            if content_key in seen_content:
                continue
            seen_content.add(content_key)

            source = result.chunk.source_title
            date_str = result.chunk.metadata.get('date_str', '')
            section = result.chunk.metadata.get('section', '')

            source_info = f"Source: {source}"
            if date_str:
                source_info += f" ({date_str})"
            if section:
                source_info += f" - {section}"

            context_parts.append(f"[{source_info}]\n{content}\n")

        context = "\n---\n".join(context_parts)

        # Try LLM-based generation first
        if self.llm and self.llm.is_available():
            logger.debug(f"Using LLM ({self.llm.get_provider()}) for response generation")
            try:
                return self.llm.generate_response(question, context)
            except Exception as e:
                logger.warning(f"LLM generation failed, falling back to template: {e}")

        # Fallback to template-based response
        return self._template_response(question, results)

    def _template_response(self, question: str, results: List[RetrievalResult]) -> str:
        """Generate a template-based response (fallback when LLM unavailable)"""
        question_lower = question.lower()
        parts = []

        # Add introduction based on question type
        if 'how' in question_lower and ('mitigat' in question_lower or 'resolv' in question_lower or 'address' in question_lower):
            parts.append("**Based on the project documentation, here's how this was addressed:**\n")
        elif 'what' in question_lower and 'risk' in question_lower:
            parts.append("**Here are the relevant risks from the project documentation:**\n")
        elif 'who' in question_lower:
            parts.append("**From the project records:**\n")
        elif 'when' in question_lower:
            parts.append("**Timeline information from project documents:**\n")
        elif 'why' in question_lower:
            parts.append("**Here's the relevant context from project documentation:**\n")
        else:
            parts.append("**From the project documentation:**\n")

        # Add content from top results
        seen_content = set()
        for i, result in enumerate(results[:3], 1):
            content = result.chunk.content.strip()
            content_key = content[:100]
            if content_key in seen_content:
                continue
            seen_content.add(content_key)

            content = self._clean_content(content)
            if len(content) > 500:
                content = content[:500] + "..."

            source = result.chunk.source_title
            date_str = result.chunk.metadata.get('date_str', '')
            section = result.chunk.metadata.get('section', '')
            source_ref = f"*{source}*"
            if date_str:
                source_ref += f" ({date_str})"
            if section and section != "Introduction":
                source_ref += f" - {section}"

            parts.append(f"**{i}. From {source_ref}:**")
            parts.append(f"{content}\n")

        if results:
            avg_score = sum(r.score for r in results[:3]) / min(3, len(results))
            if avg_score > 0.1:
                all_terms = []
                for r in results[:3]:
                    all_terms.extend(r.match_terms)
                unique_terms = list(set(all_terms))[:5]
                if unique_terms:
                    parts.append(f"\n*Key terms matched: {', '.join(unique_terms)}*")

        return "\n".join(parts)

    def _clean_content(self, content: str) -> str:
        """Clean content for display"""
        # Remove markdown artifacts
        content = content.replace('###', '').replace('##', '').replace('#', '')

        # Remove excessive whitespace
        lines = [line.strip() for line in content.split('\n')]
        lines = [line for line in lines if line]
        content = '\n'.join(lines)

        return content

    def _format_sources(self, results: List[RetrievalResult]) -> List[Dict]:
        """Format sources for response"""
        sources = []
        seen = set()

        for result in results:
            source_key = result.chunk.source_file
            if source_key in seen:
                continue
            seen.add(source_key)

            sources.append({
                'title': result.chunk.source_title,
                'file': result.chunk.source_file,
                'section': result.chunk.metadata.get('section', ''),
                'date': result.chunk.metadata.get('date_str', ''),
                'document_type': result.chunk.metadata.get('document_type', 'General'),
                'relevance': round(result.score, 3)
            })

        return sources[:5]

    def _calculate_confidence(self, results: List[RetrievalResult]) -> float:
        """Calculate confidence based on retrieval scores"""
        if not results:
            return 0.0

        # Average top 3 scores
        top_scores = [r.score for r in results[:3]]
        avg_score = sum(top_scores) / len(top_scores)

        # For hybrid retrieval, scores are already normalized (0-1)
        # For TF-IDF only, normalize
        if self.vector_store and self.vector_store.is_initialized:
            confidence = avg_score
        else:
            confidence = min(1.0, avg_score * 5)

        # Boost if we have multiple good matches
        if len(results) >= 3 and all(r.score > 0.3 for r in results[:3]):
            confidence = min(1.0, confidence * 1.2)

        return round(confidence, 2)

    def get_stats(self) -> Dict:
        """Get RAG engine statistics"""
        stats = {
            'initialized': self.is_initialized,
            **self.store.stats()
        }

        if self.vector_store:
            stats['vector_store'] = self.vector_store.get_stats()
        else:
            stats['vector_store'] = {'initialized': False, 'reason': 'Not enabled or failed to initialize'}

        if self.llm:
            stats['llm'] = {
                'available': self.llm.is_available(),
                'provider': self.llm.get_provider()
            }
        else:
            stats['llm'] = {'available': False}

        return stats
