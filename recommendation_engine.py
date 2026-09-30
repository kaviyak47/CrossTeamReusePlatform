"""
recommendation_engine.py

Processes cross-team duplicate findings and assigns reuse recommendations
based on similarity score thresholds.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def determine_priority(similarity_percentage: float) -> str:
    """
    Categorize priority based on similarity percentage:
      - HIGH:   >= 80%
      - MEDIUM: 60% – 79.99%
      - LOW:    < 60%
    """
    if similarity_percentage >= 80.0:
        return "HIGH"
    elif similarity_percentage >= 60.0:
        return "MEDIUM"
    else:
        return "LOW"


def generate_recommendations(
    findings_path: str = "cross_team_findings.json",
    output_path: str = "reuse_recommendations.json",
) -> list[dict[str, Any]]:
    """
    Reads cross-team findings, assigns priority and recommendations,
    and outputs structured recommendation records.
    """
    input_file = Path(findings_path)
    if not input_file.exists():
        raise FileNotFoundError(f"Findings file not found: {findings_path}")

    with open(input_file, "r", encoding="utf-8") as f:
        findings: list[dict[str, Any]] = json.load(f)

    recommendations: list[dict[str, Any]] = []

    for item in findings:
        similarity = float(item.get("similarity_percentage", 0.0))
        priority = determine_priority(similarity)

        # Generate recommendation text for HIGH and MEDIUM priority
        if priority in ("HIGH", "MEDIUM"):
            recommendation_text = (
                "Review the existing implementation before developing similar functionality."
            )
        else:
            recommendation_text = "Low similarity detected; reuse review is optional."

        rec = {
            "source_team": item.get("source_team"),
            "source_file": item.get("source_file"),
            "source_function": item.get("source_function"),
            "source_lines": item.get("source_lines"),
            "matched_team": item.get("matched_team"),
            "matched_file": item.get("matched_file"),
            "matched_function": item.get("matched_function"),
            "matched_lines": item.get("matched_lines"),
            "similarity_percentage": similarity,
            "priority": priority,
            "recommendation": recommendation_text,
            "duplicated_lines": item.get("duplicated_lines"),
            "match_type": item.get("match_type"),
            "reasons": item.get("reasons"),
            "evidence": item.get("evidence"),
        }
        recommendations.append(rec)

    # Save to JSON file
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(recommendations, f, indent=2)

    return recommendations


def main() -> None:
    input_file = "cross_team_findings.json"
    output_file = "reuse_recommendations.json"

    print(f"Reading cross-team findings: {input_file}")
    recommendations = generate_recommendations(input_file, output_file)
    print(f"Generated {len(recommendations)} reuse recommendation(s).")
    print(f"Saved recommendations to: {output_file}")


if __name__ == "__main__":
    main()
