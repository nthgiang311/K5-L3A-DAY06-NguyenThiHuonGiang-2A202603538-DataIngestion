
"""Local sentence-transformers embedding adapter."""
from sentence_transformers import SentenceTransformer


class MyEmbedder:
    """Generate real, dense embeddings using a local SentenceTransformer model."""

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self.model = SentenceTransformer(model_name)
        self.dimensions = self.model.get_embedding_dimension()

        if not self.dimensions:
            raise ValueError("Could not determine embedding dimensions")

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        vectors = self.model.encode(
            texts,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return vectors.tolist()

    def embed_query(self, question: str) -> list[float]:
        vectors = self.model.encode(
            [question],
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return vectors[0].tolist()
