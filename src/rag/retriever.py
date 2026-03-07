"""
Document Retriever for RAG
Uses TF-IDF and keyword matching to find relevant chunks.
"""

import re
import math
from collections import Counter
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass

from .document_store import DocumentStore, DocumentChunk


@dataclass
class RetrievalResult:
    """Result from retrieval"""
    chunk: DocumentChunk
    score: float
    match_terms: List[str]

    def to_dict(self) -> Dict:
        return {
            'chunk_id': self.chunk.chunk_id,
            'content': self.chunk.content,
            'source': self.chunk.source_title,
            'score': self.score,
            'match_terms': self.match_terms,
            'metadata': self.chunk.metadata
        }


class DocumentRetriever:
    """
    Retrieves relevant document chunks using TF-IDF scoring.
    """

    # Common English stop words
    STOP_WORDS = {
        'a', 'an', 'and', 'are', 'as', 'at', 'be', 'by', 'for', 'from',
        'has', 'he', 'in', 'is', 'it', 'its', 'of', 'on', 'or', 'that',
        'the', 'to', 'was', 'were', 'will', 'with', 'what', 'how', 'who',
        'when', 'where', 'why', 'can', 'could', 'do', 'does', 'did', 'have',
        'had', 'this', 'these', 'those', 'i', 'you', 'we', 'they', 'me',
        'him', 'her', 'us', 'them', 'my', 'your', 'our', 'their', 'about',
        'tell', 'please', 'would', 'should', 'been', 'being', 'some', 'any'
    }

    # Project-specific important terms to boost
    IMPORTANT_TERMS = {
        'risk', 'risks', 'mitigation', 'mitigated', 'stream', 'ewm', 'sd',
        'delay', 'delayed', 'issue', 'issues', 'problem', 'problems',
        'mousumi', 'nayan', 'raj', 'ryan', 'dhyanesh', 'lakshmi', 'jhanvi',
        'voice', 'picking', 'cr', 'change', 'request', 'defect', 'bug',
        'quality', 'velocity', 'sprint', 'uat', 'go-live', 'milestone',
        'budget', 'cost', 'timeline', 'schedule', 'resource', 'team',
        'left', 'joined', 'departure', 'arrived', 'status', 'progress'
    }

    def __init__(self, document_store: DocumentStore):
        self.store = document_store
        self.idf_cache: Dict[str, float] = {}
        self.term_index: Dict[str, List[str]] = {}  # term -> [chunk_ids]
        self._build_index()

    def _build_index(self):
        """Build TF-IDF index"""
        chunks = self.store.get_all_chunks()
        if not chunks:
            return

        # Build document frequency
        doc_freq: Counter = Counter()
        for chunk in chunks:
            terms = set(self._tokenize(chunk.content))
            for term in terms:
                doc_freq[term] += 1
                if term not in self.term_index:
                    self.term_index[term] = []
                self.term_index[term].append(chunk.chunk_id)

        # Calculate IDF
        num_docs = len(chunks)
        for term, freq in doc_freq.items():
            self.idf_cache[term] = math.log(num_docs / (1 + freq))

    def _tokenize(self, text: str) -> List[str]:
        """Tokenize text into terms"""
        # Convert to lowercase and extract words
        text = text.lower()
        words = re.findall(r'\b[a-z][a-z0-9-]*\b', text)

        # Filter stop words and very short words
        return [w for w in words if w not in self.STOP_WORDS and len(w) > 2]

    def _calculate_tf(self, term: str, terms: List[str]) -> float:
        """Calculate term frequency"""
        if not terms:
            return 0
        return terms.count(term) / len(terms)

    def _calculate_tfidf(self, term: str, terms: List[str]) -> float:
        """Calculate TF-IDF score for a term"""
        tf = self._calculate_tf(term, terms)
        idf = self.idf_cache.get(term, 0)
        return tf * idf

    def retrieve(self, query: str, top_k: int = 5,
                 min_score: float = 0.01) -> List[RetrievalResult]:
        """
        Retrieve most relevant chunks for a query.

        Args:
            query: Search query
            top_k: Maximum number of results
            min_score: Minimum score threshold

        Returns:
            List of RetrievalResult sorted by relevance
        """
        query_terms = self._tokenize(query)
        if not query_terms:
            return []

        # Boost important terms
        boosted_terms = []
        for term in query_terms:
            boosted_terms.append(term)
            if term in self.IMPORTANT_TERMS:
                boosted_terms.append(term)  # Add twice for boost

        results = []
        chunks = self.store.get_all_chunks()

        for chunk in chunks:
            chunk_terms = self._tokenize(chunk.content)
            score, match_terms = self._score_chunk(boosted_terms, chunk_terms, chunk)

            if score >= min_score:
                results.append(RetrievalResult(
                    chunk=chunk,
                    score=score,
                    match_terms=match_terms
                ))

        # Sort by score descending
        results.sort(key=lambda r: r.score, reverse=True)

        return results[:top_k]

    def _score_chunk(self, query_terms: List[str],
                     chunk_terms: List[str],
                     chunk: DocumentChunk) -> Tuple[float, List[str]]:
        """Score a chunk against query terms"""
        if not chunk_terms:
            return 0.0, []

        score = 0.0
        match_terms = []

        # TF-IDF scoring
        for term in set(query_terms):
            if term in chunk_terms:
                tfidf = self._calculate_tfidf(term, chunk_terms)
                # Boost for important terms
                if term in self.IMPORTANT_TERMS:
                    tfidf *= 1.5
                score += tfidf
                if term not in match_terms:
                    match_terms.append(term)

        # Bonus for exact phrase matches
        query_text = ' '.join(query_terms)
        chunk_text = chunk.content.lower()
        if query_text in chunk_text:
            score *= 1.5

        # Bonus for matching multiple consecutive terms
        for i in range(len(query_terms) - 1):
            bigram = f"{query_terms[i]} {query_terms[i+1]}"
            if bigram in chunk_text:
                score *= 1.2

        return score, match_terms

    def retrieve_by_keywords(self, keywords: List[str],
                             top_k: int = 5) -> List[RetrievalResult]:
        """Retrieve chunks containing specific keywords"""
        results = []
        chunks = self.store.get_all_chunks()

        for chunk in chunks:
            chunk_lower = chunk.content.lower()
            matched = [kw for kw in keywords if kw.lower() in chunk_lower]

            if matched:
                score = len(matched) / len(keywords)
                results.append(RetrievalResult(
                    chunk=chunk,
                    score=score,
                    match_terms=matched
                ))

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:top_k]

    def search(self, query: str, top_k: int = 5) -> List[Dict]:
        """Search and return formatted results"""
        results = self.retrieve(query, top_k)
        return [r.to_dict() for r in results]
