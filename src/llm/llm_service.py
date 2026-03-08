"""
LLM Service
Provides LLM-powered query understanding and response generation.
"""

import os
import logging
from typing import List, Dict, Optional, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class LLMConfig:
    """LLM configuration"""
    provider: str = "anthropic"
    model: str = "claude-sonnet-4-20250514"
    api_key: Optional[str] = None
    max_tokens: int = 2048
    temperature: float = 0.3

    def __post_init__(self):
        if not self.api_key:
            self.api_key = os.getenv("ANTHROPIC_API_KEY")


class LLMService:
    """
    LLM Service for intelligent query processing and response generation.
    Supports Anthropic Claude API.
    """

    def __init__(self, config: LLMConfig = None):
        self.config = config or LLMConfig()
        self.client = None
        self._initialize_client()

    def _initialize_client(self):
        """Initialize the LLM client"""
        if not self.config.api_key:
            logger.warning("No API key provided. LLM features will be disabled.")
            return

        if self.config.provider == "anthropic":
            try:
                import anthropic
                self.client = anthropic.Anthropic(api_key=self.config.api_key)
                logger.info(f"Anthropic client initialized with model: {self.config.model}")
            except ImportError:
                logger.error("anthropic package not installed. Run: pip install anthropic")
            except Exception as e:
                logger.error(f"Failed to initialize Anthropic client: {e}")

    def is_available(self) -> bool:
        """Check if LLM service is available"""
        return self.client is not None

    def generate_response(
        self,
        query: str,
        context: str,
        system_prompt: str = None
    ) -> str:
        """
        Generate a response using retrieved context.

        Args:
            query: User's question
            context: Retrieved context from knowledge graph/documents
            system_prompt: Optional system prompt override

        Returns:
            Generated response string
        """
        if not self.client:
            return self._fallback_response(query, context)

        default_system = """You are a helpful project assistant for the ABC Inc. SAP S/4HANA Migration Project.
Your role is to answer questions about the project based on the provided context from project documents.

Guidelines:
- Answer based ONLY on the provided context. Do not make up information.
- If the context doesn't contain enough information, say so clearly.
- Be concise but thorough. Use bullet points for lists.
- Reference specific dates, names, and facts from the context when available.
- Format responses with markdown for readability.
- If asked about risks or issues, provide actionable insights when possible."""

        system = system_prompt or default_system

        user_message = f"""Based on the following project context, please answer the question.

**Question:** {query}

**Project Context:**
{context}

Please provide a clear, helpful answer based on this context."""

        try:
            response = self.client.messages.create(
                model=self.config.model,
                max_tokens=self.config.max_tokens,
                temperature=self.config.temperature,
                system=system,
                messages=[
                    {"role": "user", "content": user_message}
                ]
            )
            return response.content[0].text
        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            return self._fallback_response(query, context)

    def generate_summary(
        self,
        data: Dict[str, Any],
        query_type: str
    ) -> str:
        """
        Generate a natural language summary from structured data.

        Args:
            data: Structured data from knowledge graph queries
            query_type: Type of query (status, trajectory, etc.)

        Returns:
            Natural language summary
        """
        if not self.client:
            return self._format_data_fallback(data)

        system = """You are a project reporting assistant. Convert structured project data into clear,
readable summaries. Be concise and highlight key information."""

        user_message = f"""Convert this project data into a clear summary.

Query Type: {query_type}

Data:
{self._format_data_for_prompt(data)}

Provide a well-formatted summary with key insights."""

        try:
            response = self.client.messages.create(
                model=self.config.model,
                max_tokens=1024,
                temperature=0.2,
                system=system,
                messages=[
                    {"role": "user", "content": user_message}
                ]
            )
            return response.content[0].text
        except Exception as e:
            logger.error(f"Summary generation failed: {e}")
            return self._format_data_fallback(data)

    def classify_intent(self, query: str) -> Dict[str, Any]:
        """
        Use LLM to classify query intent more accurately.

        Args:
            query: User's question

        Returns:
            Dict with intent classification and extracted entities
        """
        if not self.client:
            return {"intent": "unknown", "entities": [], "confidence": 0.0}

        system = """You are a query classifier for a project management system.
Analyze user queries and extract:
1. Intent type (status, trajectory, comparison, causal, predictive, entity_lookup, relationship, aggregation, timeline)
2. Entities mentioned (people, streams, metrics, dates, risks, change requests)
3. Time references

Respond in JSON format only."""

        user_message = f"""Classify this query:
"{query}"

Respond with JSON:
{{"intent": "type", "entities": [{{"type": "Person/Stream/Metric/etc", "value": "name"}}], "dates": ["any dates"], "confidence": 0.0-1.0}}"""

        try:
            response = self.client.messages.create(
                model=self.config.model,
                max_tokens=512,
                temperature=0.1,
                system=system,
                messages=[
                    {"role": "user", "content": user_message}
                ]
            )
            import json
            text = response.content[0].text
            # Extract JSON from response
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[1].split("```")[0]
            return json.loads(text.strip())
        except Exception as e:
            logger.error(f"Intent classification failed: {e}")
            return {"intent": "unknown", "entities": [], "confidence": 0.0}

    def _fallback_response(self, query: str, context: str) -> str:
        """Generate a basic response when LLM is unavailable"""
        if not context or context.strip() == "":
            return "I couldn't find relevant information to answer your question."

        # Extract first few relevant sentences
        lines = [l.strip() for l in context.split('\n') if l.strip()]
        if not lines:
            return "I found some context but couldn't format a response."

        response_parts = ["**From project documentation:**\n"]
        for line in lines[:5]:
            if len(line) > 20:
                response_parts.append(f"- {line[:300]}{'...' if len(line) > 300 else ''}")

        return "\n".join(response_parts)

    def _format_data_for_prompt(self, data: Any, indent: int = 0) -> str:
        """Format data for inclusion in prompts"""
        if isinstance(data, dict):
            lines = []
            for k, v in data.items():
                if isinstance(v, (dict, list)):
                    lines.append(f"{'  ' * indent}{k}:")
                    lines.append(self._format_data_for_prompt(v, indent + 1))
                else:
                    lines.append(f"{'  ' * indent}{k}: {v}")
            return "\n".join(lines)
        elif isinstance(data, list):
            lines = []
            for item in data[:10]:  # Limit to 10 items
                lines.append(f"{'  ' * indent}- {self._format_data_for_prompt(item, indent)}")
            return "\n".join(lines)
        else:
            return str(data)

    def _format_data_fallback(self, data: Dict) -> str:
        """Format data without LLM"""
        return f"**Results:**\n{self._format_data_for_prompt(data)}"
