"""
Main Application Entry Point
Project Knowledge Graph Chatbot
"""

import sys
import logging
from pathlib import Path
from datetime import datetime

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def setup_system(data_directory: str = None):
    """
    Initialize the complete system.

    Args:
        data_directory: Path to the project data files

    Returns:
        Tuple of (chat_engine, kg_builder, metrics_store)
    """
    from src.ingestion.pipeline import create_default_pipeline
    from src.knowledge_graph.builder import KnowledgeGraphBuilder
    from src.time_series.metrics_store import TimeSeriesMetricsStore
    from src.inference.query_engine import TemporalQueryEngine
    from src.inference.risk_predictor import RiskPredictor
    from src.chatbot.chat_engine import ChatEngine

    logger.info("Initializing Project KG Chatbot System...")

    # Step 1: Create ingestion pipeline
    logger.info("Creating ingestion pipeline...")
    pipeline = create_default_pipeline()

    # Step 2: Ingest data if directory provided
    if data_directory:
        data_path = Path(data_directory)
        if data_path.exists():
            logger.info(f"Ingesting data from {data_path}...")
            documents = pipeline.ingest_directory(data_path)
            logger.info(f"Ingested {len(documents)} documents")
        else:
            logger.warning(f"Data directory not found: {data_path}")
            documents = []
    else:
        documents = []

    # Step 3: Build knowledge graph
    logger.info("Building knowledge graph...")
    kg_builder = KnowledgeGraphBuilder()

    if documents:
        kg_builder.build_from_documents(documents)
        logger.info(f"Graph built with {kg_builder.graph.graph.number_of_nodes()} nodes")

    # Step 4: Initialize metrics store
    logger.info("Initializing metrics store...")
    metrics_store = TimeSeriesMetricsStore()

    # Populate metrics from documents
    for doc in documents:
        if doc.metrics:
            for metric_name, value in doc.metrics.items():
                if value is not None:
                    metrics_store.add_metric(
                        metric_name,
                        doc.timestamp,
                        float(value) if isinstance(value, (int, float)) else 0
                    )

    # Step 5: Create query engine
    logger.info("Creating query engine...")
    query_engine = TemporalQueryEngine(
        kg_builder.get_graph(),
        kg_builder.get_snapshots(),
        metrics_store
    )

    # Step 6: Create risk predictor
    logger.info("Creating risk predictor...")
    risk_predictor = RiskPredictor(query_engine, metrics_store)

    # Step 7: Create chat engine
    logger.info("Creating chat engine...")
    chat_engine = ChatEngine(
        query_engine,
        risk_predictor,
        metrics_store
    )

    logger.info("System initialization complete!")

    return chat_engine, kg_builder, metrics_store


def run_demo():
    """Run interactive demo"""
    print("\n" + "="*60)
    print("  Project Knowledge Graph Chatbot - Demo")
    print("="*60)

    # Try to find data directory
    possible_paths = [
        Path("../ABC Inc. Simulacra"),
        Path("./ABC Inc. Simulacra"),
        Path("C:/Users/shubhashis.sengupta/TestClaude/ABC Inc. Simulacra"),
    ]

    data_dir = None
    for path in possible_paths:
        if path.exists():
            data_dir = str(path)
            break

    # Initialize system
    chat_engine, kg_builder, metrics_store = setup_system(data_dir)

    print("\n" + "-"*60)
    print("System Ready! Example queries you can ask:")
    print("-"*60)
    for i, example in enumerate(chat_engine.get_examples()[:6], 1):
        print(f"  {i}. {example}")

    print("\nType 'quit' to exit, 'examples' for more examples")
    print("-"*60)

    # Interactive loop
    while True:
        try:
            user_input = input("\nYou: ").strip()

            if not user_input:
                continue

            if user_input.lower() in ['quit', 'exit', 'q']:
                print("Goodbye!")
                break

            if user_input.lower() == 'examples':
                print("\nExample queries:")
                for example in chat_engine.get_examples():
                    print(f"  - {example}")
                continue

            if user_input.lower() == 'clear':
                chat_engine.clear_context()
                print("Conversation context cleared.")
                continue

            # Process query
            response = chat_engine.chat(user_input)

            print(f"\nAssistant: {response.answer}")

            if response.follow_up_questions:
                print("\nYou might also ask:")
                for q in response.follow_up_questions:
                    print(f"  - {q}")

        except KeyboardInterrupt:
            print("\n\nGoodbye!")
            break
        except Exception as e:
            logger.error(f"Error: {e}")
            print(f"\nError processing query: {e}")


def run_streamlit():
    """Launch Streamlit UI"""
    import subprocess
    subprocess.run([
        sys.executable, "-m", "streamlit", "run",
        "app_streamlit.py"
    ])


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Project KG Chatbot")
    parser.add_argument(
        "--mode",
        choices=["demo", "streamlit", "api"],
        default="demo",
        help="Run mode"
    )
    parser.add_argument(
        "--data",
        type=str,
        help="Path to data directory"
    )

    args = parser.parse_args()

    if args.mode == "demo":
        run_demo()
    elif args.mode == "streamlit":
        run_streamlit()
    elif args.mode == "api":
        print("API mode not yet implemented. Use demo mode for now.")
