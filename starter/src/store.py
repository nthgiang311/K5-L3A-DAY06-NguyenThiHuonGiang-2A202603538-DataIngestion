"""PostgreSQL + pgvector storage and cosine-similarity search."""
from typing import Any

import psycopg
from pgvector.psycopg import register_vector
from psycopg.types.json import Jsonb
from psycopg import sql

from .models import Chunk


class PgVectorStore:
    def __init__(self, database_url: str, dimensions: int) -> None:
        if not database_url:
            raise ValueError("DATABASE_URL must not be empty")
        if not isinstance(dimensions, int) or dimensions <= 0:
            raise ValueError("dimensions must be a positive integer")

        self.database_url = database_url
        self.dimensions = dimensions

    def _connect(self):
        conn = psycopg.connect(self.database_url)
        register_vector(conn)
        return conn

    def create_schema(self) -> None:
        with self._connect() as conn:
            conn.execute("CREATE EXTENSION IF NOT EXISTS vector")

            create_table = sql.SQL("""
                CREATE TABLE IF NOT EXISTS chunks (
                    strategy TEXT NOT NULL,
                    chunk_id TEXT NOT NULL,
                    document_id TEXT NOT NULL,
                    source TEXT NOT NULL,
                    page INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    metadata JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                    embedding VECTOR({}) NOT NULL,
                    PRIMARY KEY (strategy, chunk_id)
                )
            """).format(sql.Literal(self.dimensions))

            conn.execute(create_table)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS chunks_strategy_document_idx
                ON chunks (strategy, document_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS chunks_metadata_idx
                ON chunks USING GIN (metadata)
            """)

    def upsert(
        self,
        strategy: str,
        chunks: list[Chunk],
        vectors: list[list[float]],
    ) -> None:
        if not strategy:
            raise ValueError("strategy must not be empty")
        if len(chunks) != len(vectors):
            raise ValueError("chunks and vectors must have the same length")
        if not chunks:
            return

        document_ids = {chunk.document_id for chunk in chunks}
        if len(document_ids) != 1:
            raise ValueError("One upsert call must contain only one document_id")

        for vector in vectors:
            if len(vector) != self.dimensions:
                raise ValueError(
                    f"Expected vector dimension {self.dimensions}, got {len(vector)}"
                )

        document_id = next(iter(document_ids))
        rows = [
            (
                strategy, chunk.chunk_id, chunk.document_id, chunk.source,
                chunk.page, chunk.text, Jsonb(chunk.metadata), vector,
            )
            for chunk, vector in zip(chunks, vectors)
        ]

        with self._connect() as conn:
            conn.execute(
                "DELETE FROM chunks WHERE strategy = %s AND document_id = %s",
                (strategy, document_id),
            )
            with conn.cursor() as cur:
                cur.executemany("""
                INSERT INTO chunks (
                    strategy, chunk_id, document_id, source,
                    page, text, metadata, embedding
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (strategy, chunk_id) DO UPDATE SET
                    document_id = EXCLUDED.document_id,
                    source = EXCLUDED.source,
                    page = EXCLUDED.page,
                    text = EXCLUDED.text,
                    metadata = EXCLUDED.metadata,
                    embedding = EXCLUDED.embedding
            """, rows)

    def search(
        self,
        strategy: str,
        query_vector: list[float],
        top_k: int = 3,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        if not strategy:
            raise ValueError("strategy must not be empty")
        if len(query_vector) != self.dimensions:
            raise ValueError(
                f"Expected query dimension {self.dimensions}, got {len(query_vector)}"
            )
        if top_k <= 0:
            raise ValueError("top_k must be positive")

        query = """
            SELECT chunk_id, document_id, source, page, text, metadata,
                   1 - (embedding <=> %s::vector) AS score
            FROM chunks
            WHERE strategy = %s
        """
        params: list[Any] = [query_vector, strategy]

        if filters:
            for key, value in filters.items():
                query += " AND metadata ->> %s = %s"
                params.extend([key, str(value)])

        query += " ORDER BY embedding <=> %s::vector LIMIT %s"
        params.extend([query_vector, top_k])

        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()

        return [
            {
                "chunk_id": row[0],
                "document_id": row[1],
                "source": row[2],
                "page": row[3],
                "text": row[4],
                "metadata": row[5],
                "score": float(row[6]),
            }
            for row in rows
        ]
