"""Run the Day 06 ingestion and A/B/C retrieval evaluation pipeline."""
import csv
import json
import os
import statistics
import time
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv

from .chunking import by_paragraph, fixed_size
from .embeddings import MyEmbedder
from .evaluation import evaluate_query, summarize
from .ingestion import load_pdf
from .store import PgVectorStore


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "outputs"
DOCUMENT_ID = "openstax_calculus_v1"
SOURCE = "OpenStax Calculus Volume 1"
FIRST_PAGE = 16
LAST_PAGE = 45
CHUNK_SIZE = 500
OVERLAP = 50


def read_json(path: Path):
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


def save_csv(path: Path, rows: list[dict], fieldnames: list[str]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def section_for_page(page_number: int) -> str:
    # Page 38 is assigned to section 1.2 because its heading starts there.
    return "1.1" if page_number <= 37 else "1.2"


def build_chunks(pages):
    strategies = {
        "A": [],
        "B": [],
        "C": [],
    }

    for page in pages:
        page.metadata["section"] = section_for_page(page.page)

        strategies["A"].extend(
            fixed_size(page, size=CHUNK_SIZE, overlap=OVERLAP)
        )
        paragraph_chunks = by_paragraph(page, max_size=CHUNK_SIZE)
        strategies["B"].extend(paragraph_chunks)
        strategies["C"].extend(paragraph_chunks)

    return strategies


def chunk_statistics(chunks):
    lengths = [len(chunk.text) for chunk in chunks]
    return {
        "chunk_count": len(chunks),
        "total_characters": sum(lengths),
        "min_length": min(lengths) if lengths else 0,
        "max_length": max(lengths) if lengths else 0,
        "mean_length": round(statistics.mean(lengths), 2) if lengths else 0,
        "median_length": round(statistics.median(lengths), 2) if lengths else 0,
    }


def main() -> None:
    load_dotenv(ROOT / ".env")
    OUTPUT.mkdir(parents=True, exist_ok=True)

    database_url = os.getenv("DATABASE_URL")
    model_name = os.getenv("EMBEDDING_MODEL")

    if not database_url:
        raise ValueError("DATABASE_URL is missing from .env")
    if not model_name:
        raise ValueError("EMBEDDING_MODEL is missing from .env")

    manifest_path = ROOT / "manifest.json"
    benchmark_path = ROOT / "benchmark.json"
    manifest = read_json(manifest_path)
    benchmark = read_json(benchmark_path)

    source_entry = next(
        item for item in manifest["sources"]
        if item["source_id"] == DOCUMENT_ID
    )

    pdf_path = ROOT / source_entry["source_path_or_url"]
    print(f"Loading PDF: {pdf_path.name}")

    all_pages = load_pdf(
        pdf_path,
        document_id=DOCUMENT_ID,
        source=SOURCE,
    )
    pages = [
        page for page in all_pages
        if FIRST_PAGE <= page.page <= LAST_PAGE and page.text.strip()
    ]

    if len(pages) < 30:
        raise ValueError(
            f"Expected at least 30 content pages, found {len(pages)}"
        )

    # Reconcile manifest character counts with the current extraction.
    page_by_number = {page.page: page for page in pages}
    for page_info in source_entry["pages"]:
        page = page_by_number.get(page_info["page_number"])
        if page:
            page_info["character_count"] = len(page.text)
    source_entry["total_characters"] = sum(
        len(page.text) for page in pages
    )
    write_json(manifest_path, manifest)

    print(f"Content pages: {len(pages)}")
    print(f"Extracted characters: {source_entry['total_characters']}")

    questions = benchmark["questions"]
    if len(questions) < 20:
        raise ValueError("Benchmark must contain at least 20 questions")

    dev_count = sum(q["split"] == "dev" for q in questions)
    test_count = sum(q["split"] == "test" for q in questions)
    if dev_count != 15 or test_count != 5:
        raise ValueError(
            f"Expected 15 dev and 5 test questions; got {dev_count} and {test_count}"
        )

    print(f"Benchmark: {len(questions)} questions ({dev_count} dev, {test_count} test)")

    print("Loading embedding model...")
    embedder = MyEmbedder(model_name)
    store = PgVectorStore(database_url, embedder.dimensions)
    store.create_schema()

    chunks_by_strategy = build_chunks(pages)
    all_traces = []
    ingestion_report = {}

    for strategy in ("A", "B", "C"):
        chunks = chunks_by_strategy[strategy]
        print(f"\nStrategy {strategy}: {len(chunks)} chunks")

        started = time.perf_counter()
        vectors = embedder.embed_documents([chunk.text for chunk in chunks])
        store.upsert(strategy, chunks, vectors)
        elapsed = time.perf_counter() - started

        ingestion_report[strategy] = {
            **chunk_statistics(chunks),
            "embedding_dimensions": embedder.dimensions,
            "ingestion_seconds": round(elapsed, 3),
            "embedding_model": model_name,
            "chunking": (
                "fixed_size_500_overlap_50"
                if strategy == "A"
                else "paragraph_max_500"
            ),
            "metadata_filter_enabled": strategy == "C",
            "storage": "PostgreSQL + pgvector",
            "similarity": "cosine",
        }

        for question in questions:
            query_vector = embedder.embed_query(question["question"])

            # Only C applies the user-provided metadata filter.
            filters = None
            if strategy == "C":
                filters = question.get("filter") or None

            hits = store.search(
                strategy=strategy,
                query_vector=query_vector,
                top_k=3,
                filters=filters,
            )

            result = evaluate_query(question, hits)
            result["strategy"] = strategy
            result["applied_filter"] = filters
            all_traces.append(result)

        print(f"  Ingestion + embedding: {elapsed:.2f} seconds")
        print(f"  Retrieval questions completed: {len(questions)}")

    # Full per-question retrieval traces.
    write_json(OUTPUT / "retrieval_traces.json", all_traces)

    # Aggregate Hit@1 and Evidence Hit@3.
    metrics = summarize(all_traces)
    write_json(OUTPUT / "retrieval_metrics.json", metrics)
    write_json(OUTPUT / "ingestion_report.json", ingestion_report)

    # Prepare the same 10 relative corpus positions for manual coherence review.
    coherence_rows = []
    for strategy, chunks in chunks_by_strategy.items():
        if not chunks:
            continue
        for sample_number in range(10):
            index = round(sample_number * (len(chunks) - 1) / 9)
            chunk = chunks[index]
            coherence_rows.append({
                "strategy": strategy,
                "sample_number": sample_number + 1,
                "chunk_id": chunk.chunk_id,
                "source": chunk.source,
                "page": chunk.page,
                "section": chunk.metadata.get("section", ""),
                "text": chunk.text,
                "coherence_score_0_to_2": "",
                "reason": "",
            })

    save_csv(
        OUTPUT / "manual_coherence.csv",
        coherence_rows,
        [
            "strategy", "sample_number", "chunk_id", "source", "page",
            "section", "text", "coherence_score_0_to_2", "reason",
        ],
    )

    # Prepare five test questions per strategy for manual grounding review.
    grounding_rows = []
    metadata_rows = []

    test_questions = [q for q in questions if q["split"] == "test"]

    for trace in all_traces:
        if trace["split"] != "test":
            continue

        for rank, hit in enumerate(trace["retrieved_hits"], start=1):
            metadata_rows.append({
                "strategy": trace["strategy"],
                "question_id": trace["question_id"],
                "rank": rank,
                "chunk_id": hit["chunk_id"],
                "document_id": hit["document_id"],
                "source": hit["source"],
                "page": hit["page"],
                "section": hit.get("metadata", {}).get("section", ""),
                "score": hit["score"],
                "filter": json.dumps(
                    trace["applied_filter"], ensure_ascii=False
                ),
            })

        grounding_rows.append({
            "strategy": trace["strategy"],
            "question_id": trace["question_id"],
            "question": trace["question"],
            "gold_page": trace["gold_page"],
            "top3": json.dumps(
                trace["retrieved_hits"], ensure_ascii=False
            ),
            "grounding_score_0_to_2": "",
            "reason": "",
        })

    save_csv(
        OUTPUT / "manual_grounding.csv",
        grounding_rows,
        [
            "strategy", "question_id", "question", "gold_page",
            "top3", "grounding_score_0_to_2", "reason",
        ],
    )

    save_csv(
        OUTPUT / "metadata_review.csv",
        metadata_rows,
        [
            "strategy", "question_id", "rank", "chunk_id",
            "document_id", "source", "page", "section", "score", "filter",
        ],
    )

    print("\nPipeline completed.")
    print(f"Output directory: {OUTPUT}")
    print("Generated:")
    print("  retrieval_traces.json")
    print("  retrieval_metrics.json")
    print("  ingestion_report.json")
    print("  manual_coherence.csv")
    print("  manual_grounding.csv")
    print("  metadata_review.csv")
    print("\nReview the traces and manually complete the assessment CSV files.")


if __name__ == "__main__":
    main()
