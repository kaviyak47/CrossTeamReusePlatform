import os
import zipfile
import shutil
from pathlib import Path

import code_similarity


SUPPORTED_EXTENSIONS = {".py"}


def extract_repository(zip_path, extract_to):
    """
    Extract a ZIP repository safely.
    """

    extract_to = Path(extract_to)
    extract_to.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zip_path, "r") as zip_ref:
        for member in zip_ref.infolist():

            member_path = extract_to / member.filename

            if not str(member_path.resolve()).startswith(
                str(extract_to.resolve())
            ):
                raise ValueError("Unsafe ZIP file.")

        zip_ref.extractall(extract_to)

    return extract_to


def find_python_files(repo_path):
    """
    Find Python files inside a repository.
    """

    python_files = []

    for root, _, files in os.walk(repo_path):

        for filename in files:

            if Path(filename).suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue

            # Ignore common generated folders
            if any(
                ignored in Path(root).parts
                for ignored in [
                    ".git",
                    ".venv",
                    "venv",
                    "__pycache__",
                    "node_modules"
                ]
            ):
                continue

            python_files.append(
                os.path.join(root, filename)
            )

    return python_files


def read_file(file_path):
    try:
        with open(
            file_path,
            "r",
            encoding="utf-8",
            errors="ignore"
        ) as f:
            return f.read()
    except OSError:
        return ""


def analyze_repository(repo_path, team_name):
    """
    Analyze all Python functions inside an uploaded repository.

    The uploaded code is treated only as text.
    It is never executed.
    """

    python_files = find_python_files(repo_path)

    repository_functions = []

    for file_path in python_files:

        code = read_file(file_path)

        if not code.strip():
            continue

        functions = code_similarity.extract_functions(code)

        relative_file = os.path.relpath(
            file_path,
            repo_path
        ).replace("\\", "/")

        for function in functions:

            repository_functions.append({
                "team": team_name,
                "file": relative_file,
                "function": function["name"],
                "code": function["code"],
                "start_line": function["start_line"],
                "end_line": function["end_line"]
            })

    return {
        "team": team_name,
        "files_scanned": len(python_files),
        "functions_found": len(repository_functions),
        "functions": repository_functions
    }


def compare_repository_with_existing(
    repository_data,
    existing_repo_path
):
    """
    Compare uploaded repository functions against
    existing team repositories.
    """

    results = []

    uploaded_functions = repository_data["functions"]
    uploaded_team = repository_data["team"]

    existing_files = find_python_files(existing_repo_path)

    for existing_file in existing_files:

        existing_code = read_file(existing_file)

        if not existing_code.strip():
            continue

        existing_functions = code_similarity.extract_functions(
            existing_code
        )

        relative_file = os.path.relpath(
            existing_file,
            existing_repo_path
        ).replace("\\", "/")

        # Determine existing team from folder name
        relative_parts = Path(
            os.path.relpath(existing_file, existing_repo_path)
        ).parts

        existing_team = (
            relative_parts[0]
            if relative_parts
            else "Unknown"
        )

        existing_team = existing_team.replace(
            "_", " "
        ).title()

        if existing_team.lower() == uploaded_team.lower():
            continue

        for uploaded in uploaded_functions:

            for existing in existing_functions:

                similarity = code_similarity.similarity_score(
                    uploaded["code"],
                    existing["code"]
                )

                if similarity < 35:
                    continue

                function_similarity = (
                    code_similarity.function_name_similarity(
                        uploaded["function"],
                        existing["name"]
                    )
                )

                matching_lines = max(
                    1,
                    round(
                        min(
                            len(uploaded["code"].splitlines()),
                            len(existing["code"].splitlines())
                        )
                        * similarity
                        / 100
                    )
                )

                acceptance = code_similarity.calculate_acceptance_score(
                    similarity,
                    function_similarity,
                    matching_lines,
                    cross_team=True
                )

                priority = code_similarity.get_priority(
                    acceptance
                )

                results.append({
                    "uploaded_team": uploaded_team,
                    "uploaded_file": uploaded["file"],
                    "uploaded_function": uploaded["function"],

                    "existing_team": existing_team,
                    "existing_file": relative_file,
                    "existing_function": existing["name"],

                    "similarity": similarity,
                    "function_similarity": function_similarity,
                    "matching_lines": matching_lines,

                    "acceptance_score": acceptance,
                    "priority": priority,

                    "uploaded_code": uploaded["code"],
                    "existing_code": existing["code"]
                })

    results.sort(
        key=lambda x: (
            x["acceptance_score"],
            x["similarity"]
        ),
        reverse=True
    )

    return results