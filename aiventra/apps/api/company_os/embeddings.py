"""CPU-local embeddings. No model download or paid request during application startup."""

import argparse
import hashlib
import math
import re
import threading
from functools import lru_cache

import httpx

from .config import settings
from .security import validate_endpoint

DIMENSIONS = 384
_lock = threading.Lock()


class EmbeddingUnavailable(Exception):
    pass


def fingerprint():
    config = settings()
    return hashlib.sha256(
        f"{config.embedding_provider}:{config.embedding_model}:{DIMENSIONS}:{config.embedding_endpoint}".encode()
    ).hexdigest()


@lru_cache(maxsize=2)
def local_model(name, cache, download=False):
    from fastembed import TextEmbedding

    with _lock:
        return TextEmbedding(name, cache_dir=cache, threads=1, local_files_only=not download)


def embed(texts: list[str]) -> list[list[float]]:
    config = settings()
    if not 1 <= len(texts) <= 32 or any(len(t) > 6000 for t in texts):
        raise ValueError("Embedding batch exceeds bounds")
    try:
        if config.embedding_provider == "fastembed":
            model = local_model(config.embedding_model, str(config.embedding_cache.resolve()))
            vectors = [v.tolist() for v in model.embed(texts, batch_size=16)]
        elif config.embedding_provider == "ollama":
            # Local only: project/private context never goes to an arbitrary embedding endpoint.
            base = validate_endpoint(config.embedding_endpoint, "localhost,127.0.0.1", local_allowed=True)
            with httpx.Client(timeout=20, trust_env=False, follow_redirects=False) as client:
                from .spending import authorize_embedding

                authorize_embedding(client, base, config.embedding_model)
                result = client.post(
                    base + "/api/embed", json={"model": config.embedding_model, "input": texts}
                )
                result.raise_for_status()
                vectors = result.json()["embeddings"]
        elif (
            config.embedding_provider == "deterministic_test"
            and config.app_env == "test"
            and config.mock_enabled
        ):
            # Explicit test adapter; hash features are NOT represented as semantic embeddings.
            vectors = []
            for text in texts:
                vector = [0.0] * DIMENSIONS
                for token in re.findall(r"\w+", text.lower()):
                    vector[int(hashlib.sha256(token.encode()).hexdigest()[:8], 16) % DIMENSIONS] += 1
                vectors.append(vector)
        else:
            raise EmbeddingUnavailable("Embeddings disabled or test adapter prohibited")
        if len(vectors) != len(texts):
            raise ValueError("Embedding count mismatch")
        normalized = []
        for vector in vectors:
            if len(vector) != DIMENSIONS or not all(math.isfinite(float(n)) for n in vector):
                raise ValueError("Embedding dimension or finite-value validation failed")
            norm = math.sqrt(sum(float(n) ** 2 for n in vector))
            if norm == 0:
                raise ValueError("Zero embedding rejected")
            normalized.append([float(n) / norm for n in vector])
        return normalized
    except EmbeddingUnavailable:
        raise
    except Exception:
        raise EmbeddingUnavailable(
            "Local embedding model unavailable; keyword retrieval remains available"
        ) from None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Explicitly install the configured local embedding model")
    parser.add_argument("--download", action="store_true", required=True)
    parser.parse_args()
    config = settings()
    local_model(config.embedding_model, str(config.embedding_cache.resolve()), download=True)
    print("Local embedding model cached; no paid provider credential used")
