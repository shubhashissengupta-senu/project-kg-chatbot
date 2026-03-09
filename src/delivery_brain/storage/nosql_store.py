"""
NoSQL Storage for Delivery Brain

Supports TinyDB (MIT license) for local storage
and MongoDB (Apache-2.0 license) for production.
"""

import os
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime
import json

logger = logging.getLogger(__name__)


class NoSQLStore:
    """
    NoSQL document store supporting TinyDB and MongoDB.

    Uses TinyDB by default for simplicity (no server required).
    Can switch to MongoDB for production deployments.
    """

    def __init__(self,
                 store_type: str = "tinydb",
                 tinydb_path: str = "./data/delivery_brain_db.json",
                 mongodb_uri: str = "mongodb://localhost:27017",
                 mongodb_database: str = "delivery_brain"):
        """
        Initialize NoSQL store.

        Args:
            store_type: "tinydb" or "mongodb"
            tinydb_path: Path to TinyDB file
            mongodb_uri: MongoDB connection URI
            mongodb_database: MongoDB database name
        """
        self.store_type = store_type
        self.tinydb_path = tinydb_path
        self.mongodb_uri = mongodb_uri
        self.mongodb_database = mongodb_database

        self._db = None
        self._documents_table = None
        self._chunks_table = None
        self._metadata_table = None

        self._initialize_store()

    def _initialize_store(self):
        """Initialize the storage backend"""
        if self.store_type == "tinydb":
            self._init_tinydb()
        elif self.store_type == "mongodb":
            self._init_mongodb()
        else:
            raise ValueError(f"Unknown store type: {self.store_type}")

    def _init_tinydb(self):
        """Initialize TinyDB"""
        try:
            from tinydb import TinyDB, Query

            # Ensure directory exists
            db_path = Path(self.tinydb_path)
            db_path.parent.mkdir(parents=True, exist_ok=True)

            self._db = TinyDB(str(db_path))
            self._documents_table = self._db.table('documents')
            self._chunks_table = self._db.table('chunks')
            self._metadata_table = self._db.table('metadata')

            logger.info(f"TinyDB initialized at {self.tinydb_path}")

        except ImportError:
            logger.error("TinyDB not available. Install with: pip install tinydb")
            raise

    def _init_mongodb(self):
        """Initialize MongoDB"""
        try:
            from pymongo import MongoClient

            client = MongoClient(self.mongodb_uri)
            self._db = client[self.mongodb_database]
            self._documents_table = self._db['documents']
            self._chunks_table = self._db['chunks']
            self._metadata_table = self._db['metadata']

            # Create indexes
            self._documents_table.create_index("document_id", unique=True)
            self._chunks_table.create_index("chunk_id", unique=True)
            self._chunks_table.create_index("document_id")

            logger.info(f"MongoDB initialized: {self.mongodb_database}")

        except ImportError:
            logger.error("pymongo not available. Install with: pip install pymongo")
            raise

    def store_document(self, document: Dict[str, Any]) -> str:
        """
        Store a document.

        Args:
            document: Document data with 'document_id' key

        Returns:
            Document ID
        """
        doc_id = document.get("document_id")
        if not doc_id:
            raise ValueError("Document must have 'document_id'")

        # Add timestamp
        document["stored_at"] = datetime.now().isoformat()

        if self.store_type == "tinydb":
            from tinydb import Query
            Doc = Query()

            # Upsert document
            existing = self._documents_table.search(Doc.document_id == doc_id)
            if existing:
                self._documents_table.update(document, Doc.document_id == doc_id)
            else:
                self._documents_table.insert(document)
        else:
            # MongoDB upsert
            self._documents_table.replace_one(
                {"document_id": doc_id},
                document,
                upsert=True
            )

        logger.debug(f"Stored document: {doc_id}")
        return doc_id

    def store_chunks(self, chunks: List[Dict[str, Any]]) -> int:
        """
        Store multiple chunks.

        Args:
            chunks: List of chunk data with 'chunk_id' keys

        Returns:
            Number of chunks stored
        """
        if not chunks:
            return 0

        # Add timestamps
        for chunk in chunks:
            chunk["stored_at"] = datetime.now().isoformat()

        if self.store_type == "tinydb":
            # TinyDB bulk insert
            self._chunks_table.insert_multiple(chunks)
        else:
            # MongoDB bulk insert with upsert
            from pymongo import UpdateOne
            operations = [
                UpdateOne(
                    {"chunk_id": chunk.get("chunk_id")},
                    {"$set": chunk},
                    upsert=True
                )
                for chunk in chunks
            ]
            self._chunks_table.bulk_write(operations)

        logger.debug(f"Stored {len(chunks)} chunks")
        return len(chunks)

    def get_document(self, document_id: str) -> Optional[Dict[str, Any]]:
        """Get a document by ID"""
        if self.store_type == "tinydb":
            from tinydb import Query
            Doc = Query()
            results = self._documents_table.search(Doc.document_id == document_id)
            return results[0] if results else None
        else:
            return self._documents_table.find_one({"document_id": document_id})

    def get_chunks_by_document(self, document_id: str) -> List[Dict[str, Any]]:
        """Get all chunks for a document"""
        if self.store_type == "tinydb":
            from tinydb import Query
            Chunk = Query()
            return self._chunks_table.search(Chunk.document_id == document_id)
        else:
            return list(self._chunks_table.find({"document_id": document_id}))

    def search_documents(self,
                         query: Dict[str, Any] = None,
                         limit: int = 100) -> List[Dict[str, Any]]:
        """
        Search documents.

        Args:
            query: Query criteria
            limit: Maximum results

        Returns:
            List of matching documents
        """
        if self.store_type == "tinydb":
            if query:
                from tinydb import Query
                Doc = Query()
                # Build query condition
                conditions = []
                for key, value in query.items():
                    conditions.append(getattr(Doc, key) == value)

                if conditions:
                    from functools import reduce
                    combined = reduce(lambda a, b: a & b, conditions)
                    results = self._documents_table.search(combined)
                else:
                    results = self._documents_table.all()
            else:
                results = self._documents_table.all()
            return results[:limit]
        else:
            cursor = self._documents_table.find(query or {}).limit(limit)
            return list(cursor)

    def delete_document(self, document_id: str) -> bool:
        """Delete a document and its chunks"""
        if self.store_type == "tinydb":
            from tinydb import Query
            Doc = Query()
            Chunk = Query()

            # Delete chunks
            self._chunks_table.remove(Chunk.document_id == document_id)
            # Delete document
            removed = self._documents_table.remove(Doc.document_id == document_id)
            return len(removed) > 0
        else:
            self._chunks_table.delete_many({"document_id": document_id})
            result = self._documents_table.delete_one({"document_id": document_id})
            return result.deleted_count > 0

    def get_statistics(self) -> Dict[str, Any]:
        """Get storage statistics"""
        if self.store_type == "tinydb":
            return {
                "store_type": "tinydb",
                "path": self.tinydb_path,
                "document_count": len(self._documents_table),
                "chunk_count": len(self._chunks_table),
            }
        else:
            return {
                "store_type": "mongodb",
                "database": self.mongodb_database,
                "document_count": self._documents_table.count_documents({}),
                "chunk_count": self._chunks_table.count_documents({}),
            }

    def clear_all(self):
        """Clear all data (use with caution)"""
        if self.store_type == "tinydb":
            self._documents_table.truncate()
            self._chunks_table.truncate()
            self._metadata_table.truncate()
        else:
            self._documents_table.delete_many({})
            self._chunks_table.delete_many({})
            self._metadata_table.delete_many({})

        logger.info("All data cleared from NoSQL store")

    def store_ingestion_metadata(self, metadata: Dict[str, Any]):
        """Store ingestion run metadata"""
        metadata["timestamp"] = datetime.now().isoformat()

        if self.store_type == "tinydb":
            self._metadata_table.insert(metadata)
        else:
            self._metadata_table.insert_one(metadata)

    def get_ingestion_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent ingestion history"""
        if self.store_type == "tinydb":
            results = self._metadata_table.all()
            # Sort by timestamp descending
            results.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
            return results[:limit]
        else:
            cursor = self._metadata_table.find().sort("timestamp", -1).limit(limit)
            return list(cursor)

    def close(self):
        """Close the database connection"""
        if self.store_type == "tinydb" and self._db:
            self._db.close()
        elif self.store_type == "mongodb" and self._db:
            self._db.client.close()
