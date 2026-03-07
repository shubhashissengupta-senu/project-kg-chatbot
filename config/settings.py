"""
Configuration settings for the Project KG Chatbot
"""
import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, Dict, Any
from dotenv import load_dotenv

load_dotenv()

# Base paths
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"
EMBEDDINGS_DIR = DATA_DIR / "embeddings"


@dataclass
class LLMConfig:
    """LLM configuration"""
    provider: str = "anthropic"  # or "openai"
    model: str = "claude-sonnet-4-20250514"
    api_key: Optional[str] = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY"))
    max_tokens: int = 4096
    temperature: float = 0.3


@dataclass
class GraphConfig:
    """Knowledge Graph configuration"""
    backend: str = "networkx"  # or "neo4j"
    neo4j_uri: str = field(default_factory=lambda: os.getenv("NEO4J_URI", "bolt://localhost:7687"))
    neo4j_user: str = field(default_factory=lambda: os.getenv("NEO4J_USER", "neo4j"))
    neo4j_password: str = field(default_factory=lambda: os.getenv("NEO4J_PASSWORD", ""))


@dataclass
class VectorStoreConfig:
    """Vector store configuration"""
    backend: str = "chromadb"
    collection_name: str = "project_documents"
    embedding_model: str = "all-MiniLM-L6-v2"
    persist_directory: str = str(EMBEDDINGS_DIR)


@dataclass
class ProjectConfig:
    """Project-specific configuration"""
    project_name: str = "ABC Inc. SAP S/4HANA Migration"
    project_start_date: str = "2025-12-01"
    project_end_date: str = "2026-04-22"
    current_date: str = "2026-03-07"  # Simulation current date

    # Known entities for extraction
    team_members: list = field(default_factory=lambda: [
        "Ambarish", "Ryan", "Dhyanesh", "Raj", "Riaz",
        "Mousumi", "Nayan", "Lakshmi", "Jhanvi", "Krutika",
        "Sandeep", "Tara", "Vipul", "Tyler", "Jones",
        "Rick", "Roshan", "Sandra", "Michael", "David", "Priya"
    ])

    streams: list = field(default_factory=lambda: ["SD", "EWM"])

    meeting_types: list = field(default_factory=lambda: [
        "Scrum", "ClientReview", "QAReview", "FinanceReview"
    ])


@dataclass
class Settings:
    """Main settings container"""
    llm: LLMConfig = field(default_factory=LLMConfig)
    graph: GraphConfig = field(default_factory=GraphConfig)
    vector_store: VectorStoreConfig = field(default_factory=VectorStoreConfig)
    project: ProjectConfig = field(default_factory=ProjectConfig)

    # Logging
    log_level: str = "INFO"

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000


# Global settings instance
settings = Settings()


def get_settings() -> Settings:
    """Get settings instance"""
    return settings
