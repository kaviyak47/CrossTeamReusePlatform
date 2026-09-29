"""
team_analyzer.py

Analyzes CloneHunter scan reports to identify cross-team code duplications.
Filters out intra-team duplicates and formats findings into clean, structured data.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def determine_team(file_path: str) -> str:
    """
    Extract the team name from a repository file path.
    Example:
        'test_repos/team_a/employee.py' -> 'Team A'
        'test_repos\\team_b\\worker.py'  -> 'Team B'
    """
    normalized_parts = Path(file_path).parts
    for part in normalized_parts:
        lower_part = part.lower()
        if lower_part.startswith("team_") or lower_part.startswith("team-"):
            return lower_part.replace("_", " ").replace("-", " ").title()
    return "Unknown Team"


def analyze_cross_team_duplicates(
    report_path: str = "test_clonehunter_report.json",
    output_path: str = "cross_team_findings.json",
) -> list[dict[str, Any]]:
    """
    Parses a CloneHunter JSON report, filters for cross-team duplicates,
    and saves the structured findings to a JSON file.
    """
    report_file = Path(report_path)
    if not report_file.exists():
        raise FileNotFoundError(f"Report file not found: {report_path}")

    with open(report_file, "r", encoding="utf-8") as f:
        raw_data = json.load(f)

    raw_findings = raw_data.get("findings", [])
    cross_team_findings: list[dict[str, Any]] = []

    for finding in raw_findings:
        func_a = finding.get("function_a", {})
        func_b = finding.get("function_b", {})
        compare = finding.get("compare", {})

        file_a = func_a.get("file", {}).get("path", "")
        file_b = func_b.get("file", {}).get("path", "")

        team_a = determine_team(file_a)
        team_b = determine_team(file_b)

        # Ignore intra-team duplicates (both files belong to the same team)
        if team_a == team_b and team_a != "Unknown Team":
            continue

        # Extract function names and line spans
        func_name_a = func_a.get("qualified_name", "unknown")
        func_name_b = func_b.get("qualified_name", "unknown")

        lines_a = f"{func_a.get('start_line', 0)}-{func_a.get('end_line', 0)}"
        lines_b = f"{func_b.get('start_line', 0)}-{func_b.get('end_line', 0)}"

        # Compute similarity percentage
        raw_score = float(finding.get("score", 0.0))
        similarity_percentage = round(raw_score * 100, 2)

        # Match type (e.g. FUNC <-> FUNC)
        kind_a = compare.get("kind_a", "UNKNOWN")
        kind_b = compare.get("kind_b", "UNKNOWN")
        match_type = f"{kind_a} <-> {kind_b}"

        # Extract diff / evidence
        diff_evidence = compare.get("diff", "")

        # Format standardized cross-team finding
        structured_finding = {
            "source_team": team_a,
            "source_file": file_a.replace("\\", "/"),
            "source_function": func_name_a,
            "source_lines": lines_a,
            "matched_team": team_b,
            "matched_file": file_b.replace("\\", "/"),
            "matched_function": func_name_b,
            "matched_lines": lines_b,
            "similarity_percentage": similarity_percentage,
            "duplicated_lines": finding.get("duplicated_lines", 0),
            "match_type": match_type,
            "reasons": finding.get("reasons", []),
            "evidence": diff_evidence,
        }

        cross_team_findings.append(structured_finding)

    # Save output to JSON
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(cross_team_findings, f, indent=2)

    return cross_team_findings


def main() -> None:
    input_report = "test_clonehunter_report.json"
    output_report = "cross_team_findings.json"

    print(f"Reading CloneHunter report: {input_report}")
    findings = analyze_cross_team_duplicates(input_report, output_report)
    print(f"Successfully processed {len(findings)} cross-team finding(s).")
    print(f"Saved results to: {output_report}")


if __name__ == "__main__":
    main()
