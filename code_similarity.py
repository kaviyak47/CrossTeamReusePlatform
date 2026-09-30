import ast
import os
import re
import math
from difflib import SequenceMatcher


SUPPORTED_EXTENSIONS = {".py"}


def clean_code(code):
    """Remove comments and normalize whitespace."""
    lines = []

    for line in code.splitlines():
        stripped = line.strip()

        if not stripped:
            continue

        if stripped.startswith("#"):
            continue

        lines.append(stripped)

    return "\n".join(lines)


def tokenize_code(code):
    """Simple tokenization for comparing source code."""
    cleaned = clean_code(code)

    return re.findall(
        r"[A-Za-z_][A-Za-z0-9_]*|\d+(?:\.\d+)?|[+\-*/%=<>!]+|[(){}\[\],.:]",
        cleaned
    )


def extract_functions(code):
    """Extract Python function names and their source."""
    functions = []

    try:
        tree = ast.parse(code)
    except SyntaxError:
        return functions

    lines = code.splitlines()

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            start = node.lineno
            end = getattr(node, "end_lineno", start)

            function_code = "\n".join(lines[start - 1:end])

            functions.append({
                "name": node.name,
                "code": function_code,
                "start_line": start,
                "end_line": end
            })

    return functions


def similarity_score(code1, code2):
    """Return similarity percentage between two code blocks."""
    tokens1 = tokenize_code(code1)
    tokens2 = tokenize_code(code2)

    if not tokens1 or not tokens2:
        return 0.0

    text1 = " ".join(tokens1)
    text2 = " ".join(tokens2)

    return round(SequenceMatcher(None, text1, text2).ratio() * 100, 2)


def function_name_similarity(name1, name2):
    """Compare two function names."""
    if not name1 or not name2:
        return 0.0

    return round(
        SequenceMatcher(None, name1.lower(), name2.lower()).ratio() * 100,
        2
    )


def calculate_acceptance_score(
    similarity,
    function_similarity,
    matching_lines,
    cross_team=True
):
    """
    Acceptance score represents how suitable the existing
    implementation is for reuse.

    It is intentionally different from similarity score.
    """

    similarity_component = min(similarity, 100) * 0.60
    function_component = min(function_similarity, 100) * 0.20

    # Evidence strength
    if matching_lines >= 10:
        evidence_component = 10
    elif matching_lines >= 5:
        evidence_component = 7
    elif matching_lines >= 2:
        evidence_component = 4
    else:
        evidence_component = 1

    cross_team_component = 10 if cross_team else 0

    score = (
        similarity_component
        + function_component
        + evidence_component
        + cross_team_component
    )

    return round(min(score, 100), 1)


def get_priority(acceptance_score):
    if acceptance_score >= 80:
        return "HIGH"
    elif acceptance_score >= 60:
        return "MEDIUM"
    else:
        return "LOW"


def analyze_uploaded_code(uploaded_code, uploaded_filename, repos_root="test_repos"):
    """
    Compare uploaded code against code belonging to other teams.
    Uploaded code is NEVER executed.
    """

    uploaded_functions = extract_functions(uploaded_code)

    results = []

    if not os.path.exists(repos_root):
        return results

    for team_name in os.listdir(repos_root):

        team_path = os.path.join(repos_root, team_name)

        if not os.path.isdir(team_path):
            continue

        for root, _, files in os.walk(team_path):

            for filename in files:

                extension = os.path.splitext(filename)[1].lower()

                if extension not in SUPPORTED_EXTENSIONS:
                    continue

                file_path = os.path.join(root, filename)

                try:
                    with open(
                        file_path,
                        "r",
                        encoding="utf-8",
                        errors="ignore"
                    ) as f:
                        existing_code = f.read()
                except OSError:
                    continue

                existing_functions = extract_functions(existing_code)

                # Function-level comparison
                if uploaded_functions and existing_functions:

                    for uploaded_function in uploaded_functions:

                        for existing_function in existing_functions:

                            code_similarity = similarity_score(
                                uploaded_function["code"],
                                existing_function["code"]
                            )

                            name_similarity = function_name_similarity(
                                uploaded_function["name"],
                                existing_function["name"]
                            )

                            if code_similarity < 35:
                                continue

                            matching_lines = max(
                                1,
                                round(
                                    min(
                                        len(uploaded_function["code"].splitlines()),
                                        len(existing_function["code"].splitlines())
                                    )
                                    * code_similarity
                                    / 100
                                )
                            )

                            acceptance = calculate_acceptance_score(
                                code_similarity,
                                name_similarity,
                                matching_lines,
                                cross_team=True
                            )

                            priority = get_priority(acceptance)

                            results.append({
                                "uploaded_file": uploaded_filename,
                                "uploaded_function": uploaded_function["name"],
                                "existing_team": team_name.replace("_", " ").title(),
                                "existing_file": os.path.relpath(
                                    file_path,
                                    repos_root
                                ).replace("\\", "/"),
                                "existing_function": existing_function["name"],
                                "similarity": code_similarity,
                                "function_similarity": name_similarity,
                                "matching_lines": matching_lines,
                                "acceptance_score": acceptance,
                                "priority": priority,
                                "uploaded_code": uploaded_function["code"],
                                "existing_code": existing_function["code"],
                            })

                else:
                    # Whole-file comparison if no functions were detected
                    similarity = similarity_score(
                        uploaded_code,
                        existing_code
                    )

                    if similarity < 35:
                        continue

                    matching_lines = max(
                        1,
                        round(
                            min(
                                len(uploaded_code.splitlines()),
                                len(existing_code.splitlines())
                            ) * similarity / 100
                        )
                    )

                    acceptance = calculate_acceptance_score(
                        similarity,
                        0,
                        matching_lines,
                        cross_team=True
                    )

                    results.append({
                        "uploaded_file": uploaded_filename,
                        "uploaded_function": "Whole file",
                        "existing_team": team_name.replace("_", " ").title(),
                        "existing_file": os.path.relpath(
                            file_path,
                            repos_root
                        ).replace("\\", "/"),
                        "existing_function": "Whole file",
                        "similarity": similarity,
                        "function_similarity": 0,
                        "matching_lines": matching_lines,
                        "acceptance_score": acceptance,
                        "priority": get_priority(acceptance),
                        "uploaded_code": uploaded_code,
                        "existing_code": existing_code,
                    })

    results.sort(
        key=lambda x: (
            x["acceptance_score"],
            x["similarity"]
        ),
        reverse=True
    )

    return results