"""
RAG Engine
Combines retrieval with LLM-powered response generation.
"""

from typing import List, Dict, Optional, TYPE_CHECKING
from dataclasses import dataclass
from pathlib import Path
import logging

from .document_store import DocumentStore
from .retriever import DocumentRetriever, RetrievalResult

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
    Uses TF-IDF retrieval with LLM-powered response generation.
    Falls back to template-based responses when LLM is unavailable.
    """

    def __init__(self, data_directory: Optional[Path] = None, llm_service: "LLMService" = None):
        self.store = DocumentStore(chunk_size=600, chunk_overlap=100)
        self.retriever: Optional[DocumentRetriever] = None
        self.llm = llm_service
        self.is_initialized = False

        if data_directory:
            self.initialize(data_directory)

    def initialize(self, data_directory: Path) -> int:
        """Initialize the RAG engine with documents"""
        data_directory = Path(data_directory)
        count = self.store.load_directory(data_directory)
        self.retriever = DocumentRetriever(self.store)
        self.is_initialized = True
        return count

    def set_llm_service(self, llm_service: "LLMService"):
        """Set or update the LLM service"""
        self.llm = llm_service
        logger.info(f"LLM service configured: {llm_service.is_available()}")

    def query(self, question: str, top_k: int = 5, allowed_doc_types: List[str] = None) -> RAGResponse:
        """
        Answer a question using RAG.

        Args:
            question: User's question
            top_k: Number of chunks to retrieve
            allowed_doc_types: List of document types user can access (for RBAC)

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

        # Retrieve relevant chunks
        results = self.retriever.retrieve(question, top_k=top_k * 2)  # Get more to filter

        # Apply RBAC filtering if allowed_doc_types is specified
        if allowed_doc_types:
            results = [
                r for r in results
                if r.chunk.metadata.get('document_type', 'General') in allowed_doc_types
            ]

        # Limit to top_k after filtering
        results = results[:top_k]

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
            logger.debug("Using LLM for response generation")
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

        # Remove table formatting if present
        if '|' in content and content.count('|') > 4:
            # Keep table but clean it
            pass

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

        # Normalize to 0-1 range (TF-IDF scores are typically small)
        confidence = min(1.0, avg_score * 5)

        # Boost if we have multiple good matches
        if len(results) >= 3 and all(r.score > 0.05 for r in results[:3]):
            confidence = min(1.0, confidence * 1.2)

        return round(confidence, 2)

    def get_stats(self) -> Dict:
        """Get RAG engine statistics"""
        return {
            'initialized': self.is_initialized,
            **self.store.stats()
        }
