"""
Streamlit Application
Interactive UI for the Project KG Chatbot.
"""

import streamlit as st
from pathlib import Path
from datetime import datetime
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd

# Page configuration
st.set_page_config(
    page_title="Project KG Chatbot",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)


@st.cache_resource
def initialize_system():
    """Initialize the chatbot system (cached)"""
    from main import setup_system

    # Find data directory
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

    return setup_system(data_dir)


def main():
    """Main Streamlit application"""

    # Header
    st.title("📊 Project Knowledge Graph Chatbot")
    st.markdown("*AI-powered insights for the ABC Inc. SAP S/4HANA Migration Project*")

    # Initialize system
    with st.spinner("Initializing system..."):
        try:
            chat_engine, kg_builder, metrics_store = initialize_system()
            system_ready = True
        except Exception as e:
            st.error(f"Error initializing system: {e}")
            system_ready = False

    if not system_ready:
        st.stop()

    # Sidebar
    with st.sidebar:
        st.header("📁 Navigation")

        page = st.radio(
            "Select View",
            ["💬 Chat", "📈 Dashboard", "🔍 Explorer", "📋 Timeline"]
        )

        st.markdown("---")

        st.header("ℹ️ System Info")
        stats = kg_builder.get_graph().get_statistics()
        st.metric("Entities", stats.get("node_count", 0))
        st.metric("Relationships", stats.get("edge_count", 0))
        st.metric("Snapshots", len(kg_builder.get_snapshots().snapshots))

        st.markdown("---")

        st.header("💡 Example Queries")
        examples = chat_engine.get_examples()[:5]
        for ex in examples:
            if st.button(ex[:40] + "...", key=ex):
                st.session_state.query = ex

    # Main content area
    if page == "💬 Chat":
        render_chat_page(chat_engine)
    elif page == "📈 Dashboard":
        render_dashboard_page(kg_builder, metrics_store)
    elif page == "🔍 Explorer":
        render_explorer_page(kg_builder)
    elif page == "📋 Timeline":
        render_timeline_page(kg_builder)


def render_chat_page(chat_engine):
    """Render chat interface"""
    st.header("💬 Chat with Your Project")

    # Initialize chat history
    if "messages" not in st.session_state:
        st.session_state.messages = []

    # Display chat history
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # Chat input
    if prompt := st.chat_input("Ask about the project..."):
        # Add user message
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # Get response
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                response = chat_engine.chat(prompt)

            st.markdown(response.answer)

            # Show follow-up questions
            if response.follow_up_questions:
                st.markdown("**You might also ask:**")
                cols = st.columns(len(response.follow_up_questions))
                for i, q in enumerate(response.follow_up_questions):
                    with cols[i]:
                        if st.button(q, key=f"followup_{i}"):
                            st.session_state.query = q
                            st.rerun()

        # Add assistant message
        st.session_state.messages.append({
            "role": "assistant",
            "content": response.answer
        })

    # Handle example query selection
    if "query" in st.session_state and st.session_state.query:
        query = st.session_state.query
        st.session_state.query = None
        st.session_state.messages.append({"role": "user", "content": query})
        st.rerun()


def render_dashboard_page(kg_builder, metrics_store):
    """Render dashboard with metrics"""
    st.header("📈 Project Dashboard")

    # Get current project state
    query_engine = kg_builder.get_snapshots()
    current_snapshot = query_engine.get_snapshot_at(datetime(2026, 3, 7))

    if current_snapshot:
        summary = current_snapshot.summary()

        # Top metrics row
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric(
                "Team Size",
                len(current_snapshot.get_nodes_by_type("Person")),
                delta=None
            )

        with col2:
            risks = [n for n in current_snapshot.get_nodes_by_type("Risk")
                    if current_snapshot.get_node(n).get("status") in ["Open", "Mitigating"]]
            st.metric("Open Risks", len(risks))

        with col3:
            defects = [n for n in current_snapshot.get_nodes_by_type("Defect")
                      if current_snapshot.get_node(n).get("status") != "Closed"]
            st.metric("Open Defects", len(defects))

        with col4:
            crs = current_snapshot.get_nodes_by_type("ChangeRequest")
            st.metric("Change Requests", len(crs))

        st.markdown("---")

        # Entity distribution
        col1, col2 = st.columns(2)

        with col1:
            st.subheader("Entity Distribution")
            entity_counts = summary.get("entity_types", {})
            if entity_counts:
                fig = px.pie(
                    values=list(entity_counts.values()),
                    names=list(entity_counts.keys()),
                    title="Entities by Type"
                )
                st.plotly_chart(fig, use_container_width=True)

        with col2:
            st.subheader("Metrics Summary")
            metrics_summary = metrics_store.summary()
            st.json(metrics_summary)

    else:
        st.warning("No snapshot data available")


def render_explorer_page(kg_builder):
    """Render entity explorer"""
    st.header("🔍 Entity Explorer")

    # Entity type selector
    graph = kg_builder.get_graph()
    stats = graph.get_statistics()
    entity_types = list(stats.get("entity_types", {}).keys())

    selected_type = st.selectbox("Select Entity Type", entity_types)

    if selected_type:
        entities = graph.get_nodes_by_type(selected_type)

        # Display as table
        if entities:
            df = pd.DataFrame(entities)

            # Show entity count
            st.info(f"Found {len(entities)} {selected_type} entities")

            # Search filter
            search = st.text_input("Search", "")
            if search:
                df = df[df.astype(str).apply(
                    lambda x: x.str.contains(search, case=False)
                ).any(axis=1)]

            st.dataframe(df, use_container_width=True)

            # Entity detail viewer
            if len(entities) > 0:
                st.subheader("Entity Details")
                entity_ids = [e.get("id") for e in entities]
                selected_entity = st.selectbox("Select Entity", entity_ids)

                if selected_entity:
                    entity_data = graph.get_node(selected_entity)
                    if entity_data:
                        st.json(entity_data)

                        # Show relationships
                        neighbors = graph.get_neighbors(selected_entity)
                        if neighbors:
                            st.subheader("Related Entities")
                            rel_df = pd.DataFrame(neighbors)
                            st.dataframe(rel_df, use_container_width=True)


def render_timeline_page(kg_builder):
    """Render project timeline"""
    st.header("📋 Project Timeline")

    # Get snapshots
    snapshots_manager = kg_builder.get_snapshots()
    snapshots_summary = snapshots_manager.summary()

    if snapshots_summary.get("snapshots"):
        # Timeline visualization
        timeline_data = []
        for snap in snapshots_summary["snapshots"]:
            timeline_data.append({
                "Date": snap["timestamp"],
                "Label": snap["label"],
                "Nodes": snap["node_count"],
                "Edges": snap["edge_count"]
            })

        df = pd.DataFrame(timeline_data)

        # Line chart
        fig = px.line(
            df,
            x="Date",
            y="Nodes",
            title="Entity Growth Over Time",
            markers=True
        )
        st.plotly_chart(fig, use_container_width=True)

        # Snapshot selector
        st.subheader("Snapshot Explorer")
        selected_date = st.selectbox(
            "Select Snapshot",
            df["Date"].tolist(),
            format_func=lambda x: x.strftime("%Y-%m-%d") if hasattr(x, 'strftime') else str(x)
        )

        if selected_date:
            snapshot = snapshots_manager.get_snapshot_at(selected_date)
            if snapshot:
                col1, col2 = st.columns(2)
                with col1:
                    st.metric("Nodes", snapshot.node_count())
                with col2:
                    st.metric("Edges", snapshot.edge_count())

                st.json(snapshot.summary())
    else:
        st.warning("No timeline data available")


if __name__ == "__main__":
    main()
