"""Evaluate retrieved evidence and preserve per-query traces."""
from typing import Any
import re


def normalize_evidence(text: str) -> str:
    """Normalize whitespace and case for evidence comparison."""
    return re.sub(r"\s+", " ", text).strip().casefold()


def contains_evidence(hit_text: str, evidence: str) -> bool:
    """Check whether a retrieved chunk contains the expected evidence."""
    if not evidence:
        return False
    return normalize_evidence(evidence) in normalize_evidence(hit_text)


def is_gold_evidence(question: dict[str, Any], hit: dict[str, Any]) -> bool:
    """Require matching source, page, and at least one accepted evidence quote."""
    gold_source = question.get("gold_source_id")
    gold_page = question.get("gold_page")

    if hit.get("document_id") != gold_source:
        return False

    if hit.get("page") != gold_page:
        return False

    evidence_items = question.get("evidence_quotes")
    if evidence_items is None:
        evidence_items = [question.get("evidence_quote", "")]

    return any(
        contains_evidence(hit.get("text", ""), evidence)
        for evidence in evidence_items
        if evidence
    )


def evaluate_query(
    question: dict[str, Any],
    hits: list[dict[str, Any]],
) -> dict[str, Any]:
    """Evaluate Hit@1 and Evidence Hit@3 while retaining the full retrieval trace."""
    top_hits = hits[:3]

    hit_at_1 = bool(top_hits and is_gold_evidence(question, top_hits[0]))
    evidence_hit_at_3 = any(
        is_gold_evidence(question, hit) for hit in top_hits
    )

    return {
        "question_id": question["id"],
        "split": question["split"],
        "question": question["question"],
        "gold_source_id": question.get("gold_source_id"),
        "gold_page": question.get("gold_page"),
        "hit_at_1": hit_at_1,
        "evidence_hit_at_3": evidence_hit_at_3,
        "retrieved_hits": top_hits,
    }


def summarize(traces: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate retrieval metrics by strategy and benchmark split."""
    summary: dict[str, Any] = {}

    for strategy in sorted({trace["strategy"] for trace in traces}):
        summary[strategy] = {}

        for split in ("dev", "test"):
            rows = [
                trace for trace in traces
                if trace["strategy"] == strategy
                and trace["split"] == split
            ]

            count = len(rows)
            summary[strategy][split] = {
                "question_count": count,
                "hit_at_1_count": sum(
                    bool(row["hit_at_1"]) for row in rows
                ),
                "hit_at_1_rate": (
                    sum(bool(row["hit_at_1"]) for row in rows) / count
                    if count else 0.0
                ),
                "evidence_hit_at_3_count": sum(
                    bool(row["evidence_hit_at_3"]) for row in rows
                ),
                "evidence_hit_at_3_rate": (
                    sum(bool(row["evidence_hit_at_3"]) for row in rows) / count
                    if count else 0.0
                ),
            }

    return summary
