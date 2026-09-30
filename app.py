"""
app.py

Flask web app for the Cross-Team Duplicate Work Detection and Reuse
Recommendation Platform.  (Phase 1: login, dashboard, show existing results)
(Phase 2: "Search existing work" page)

It only READS reuse_recommendations.json. The CloneHunter pipeline
(team_analyzer.py -> recommendation_engine.py) is not changed.
"""

from __future__ import annotations

import json
import os
import repo_analyzer
from werkzeug.utils import secure_filename
import code_similarity
from functools import wraps
from pathlib import Path
from typing import Any

from flask import Flask, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

import db
import search_engine  # Phase 2: local TF-IDF search

BASE_DIR = Path(__file__).resolve().parent
RECOMMENDATIONS_FILE = BASE_DIR / "reuse_recommendations.json"
DATABASE_FILE = BASE_DIR / "data" / "platform.db"

app = Flask(__name__)
UPLOAD_FOLDER = os.path.join(app.root_path, "uploads")
ALLOWED_EXTENSIONS = {".py"}
MAX_UPLOAD_SIZE = 2 * 1024 * 1024

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_SIZE
# Set SECRET_KEY in the environment for anything other than local testing.
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-only-change-me")

PRIORITY_ORDER = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}

# Plain-language wording for the reason codes CloneHunter writes into the JSON.
# Unknown codes are shown as-is (underscores replaced), so nothing is hidden.
REASON_LABELS = {
    "func_threshold": "Whole-function similarity is above the detection threshold",
    "min_window_hits": "Enough matching code windows were found between the two functions",
}


# ---------------------------------------------------------------------------
# Reading reuse_recommendations.json
# ---------------------------------------------------------------------------

def parse_diff(evidence: str | None) -> list[dict[str, str]]:
    """Turn a unified-diff string into rows the template can colour."""
    rows: list[dict[str, str]] = []
    lines = (evidence or "").splitlines()
    for index, line in enumerate(lines):
        # The first two lines are the "---" / "+++" file headers; skip them.
        if index < 2 and (line.startswith("---") or line.startswith("+++")):
            continue
        if line.startswith("@@"):
            rows.append({"kind": "hunk", "sign": "", "text": line})
        elif line.startswith("+"):
            rows.append({"kind": "add", "sign": "+", "text": line[1:]})
        elif line.startswith("-"):
            rows.append({"kind": "del", "sign": "-", "text": line[1:]})
        else:
            rows.append({"kind": "ctx", "sign": "", "text": line[1:] if line.startswith(" ") else line})
    return rows


def prepare_recommendation(index: int, item: dict[str, Any]) -> dict[str, Any]:
    """Shape one JSON record into what the templates need."""
    try:
        similarity = float(item.get("similarity_percentage", 0.0))
    except (TypeError, ValueError):
        similarity = 0.0

    reasons = [
        REASON_LABELS.get(code, str(code).replace("_", " "))
        for code in (item.get("reasons") or [])
    ]

    return {
        "id": index,
        "priority": str(item.get("priority") or "LOW").upper(),
        "similarity": similarity,
        "bar_width": max(0.0, min(100.0, similarity)),
        # Acceptance score is not produced by the current pipeline yet.
        # If a record ever carries one, it is shown; otherwise the page says "not scored".
        "acceptance": item.get("acceptance_score"),
        "source": {
            "team": item.get("source_team") or "Unknown team",
            "file": item.get("source_file") or "-",
            "function": item.get("source_function") or "-",
            "lines": item.get("source_lines") or "-",
        },
        "matched": {
            "team": item.get("matched_team") or "Unknown team",
            "file": item.get("matched_file") or "-",
            "function": item.get("matched_function") or "-",
            "lines": item.get("matched_lines") or "-",
        },
        "match_type": item.get("match_type") or "",
        "duplicated_lines": item.get("duplicated_lines"),
        "reasons": reasons,
        "recommendation": item.get("recommendation") or "",
        "diff": parse_diff(item.get("evidence")),
    }


def load_recommendations() -> tuple[list[dict[str, Any]], str | None]:
    """Return (recommendations, error_message). Never raises for a bad file."""
    if not RECOMMENDATIONS_FILE.exists():
        return [], (
            f"{RECOMMENDATIONS_FILE.name} was not found. Run team_analyzer.py and "
            "then recommendation_engine.py to create it."
        )
    try:
        with open(RECOMMENDATIONS_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        return [], f"Could not read {RECOMMENDATIONS_FILE.name}: {exc}"

    if not isinstance(raw, list):
        return [], f"{RECOMMENDATIONS_FILE.name} should contain a list of recommendations."

    recommendations = [
        prepare_recommendation(i, item) for i, item in enumerate(raw) if isinstance(item, dict)
    ]
    recommendations.sort(
        key=lambda r: (PRIORITY_ORDER.get(r["priority"], 3), -r["similarity"])
    )
    return recommendations, None


# ---------------------------------------------------------------------------
# Login handling
# ---------------------------------------------------------------------------

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "username" not in session:
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)

    return wrapped


def safe_next_url(target: str | None) -> str:
    """Only allow redirects to pages inside this app."""
    if target and target.startswith("/") and not target.startswith("//"):
        return target
    return url_for("dashboard")


@app.route("/")
def index():
    if "username" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if "username" in session:
        return redirect(url_for("dashboard"))

    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = db.get_user(DATABASE_FILE, username)
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["username"] = user["username"]
            session["display_name"] = user["display_name"]
            return redirect(safe_next_url(request.args.get("next")))
        error = "Username or password is incorrect."

    return render_template("login.html", error=error)


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@app.route("/dashboard")
@login_required
def dashboard():
    recommendations, load_error = load_recommendations()
    counts = {"ALL": len(recommendations), "HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for rec in recommendations:
        if rec["priority"] in counts:
            counts[rec["priority"]] += 1
    return render_template(
        "dashboard.html",
        recommendations=recommendations,
        counts=counts,
        load_error=load_error,
    )


# ---------------------------------------------------------------------------
# Phase 2: Search existing work
# ---------------------------------------------------------------------------

@app.route("/search")
@login_required
def search():
    """
    Search page. The query comes from the URL, e.g. /search?q=salary
    (a normal GET form), so results can be bookmarked or refreshed.
    """
    query = request.args.get("q", "").strip()
    results = []
    searched = False          # True once the user has actually submitted a query
    too_vague = False         # True if the query only had ignorable words like "the"
    recommendations, load_error = load_recommendations()

    if query and not load_error:
        searched = True
        if not search_engine.words(query) and not search_engine.joined_pairs(query):
            too_vague = True
        else:
            results = search_engine.search(query, recommendations)

    return render_template(
        "search.html",
        query=query,
        results=results,
        searched=searched,
        too_vague=too_vague,
        load_error=load_error,
        total_findings=len(recommendations),
    )


db.init_db(DATABASE_FILE)
@app.route("/check-file", methods=["GET", "POST"])
@login_required
def check_file():

    if request.method == "GET":
        return render_template("check_file.html")

    uploaded_file = request.files.get("code_file")

    if not uploaded_file or not uploaded_file.filename:
        return render_template(
            "check_file.html",
            error="Please select a Python file."
        )

    original_filename = uploaded_file.filename

    extension = os.path.splitext(original_filename)[1].lower()

    if extension not in ALLOWED_EXTENSIONS:
        return render_template(
            "check_file.html",
            error="Only Python (.py) files are supported."
        )

    filename = secure_filename(original_filename)

    if not filename:
        return render_template(
            "check_file.html",
            error="Invalid filename."
        )

    try:
        code = uploaded_file.read().decode(
            "utf-8",
            errors="ignore"
        )
    except Exception:
        return render_template(
            "check_file.html",
            error="Could not read the uploaded file."
        )

    if not code.strip():
        return render_template(
            "check_file.html",
            error="The uploaded file is empty."
        )

    results = code_similarity.analyze_uploaded_code(
        code,
        filename,
        repos_root=os.path.join(app.root_path, "test_repos")
    )

    return render_template(
        "check_file_results.html",
        filename=filename,
        results=results
    )


# ---------------------------------------------------------------------------
# Phase 4: Repository analysis
# ---------------------------------------------------------------------------

@app.route("/analyze-repository", methods=["GET", "POST"])
@login_required
def analyze_repository():

    if request.method == "GET":
        return render_template("analyze_repo.html")

    uploaded_file = request.files.get("repo_file")
    team_name = request.form.get("team_name", "").strip()

    if not team_name:
        return render_template(
            "analyze_repo.html",
            error="Please enter a team name."
        )

    if not uploaded_file or not uploaded_file.filename:
        return render_template(
            "analyze_repo.html",
            error="Please select a repository ZIP file."
        )

    if not uploaded_file.filename.lower().endswith(".zip"):
        return render_template(
            "analyze_repo.html",
            error="Only ZIP files are supported."
        )

    upload_dir = Path(app.root_path) / "uploads"
    upload_dir.mkdir(exist_ok=True)

    zip_path = upload_dir / secure_filename(
        uploaded_file.filename
    )

    extract_dir = upload_dir / (
        "repository_" + team_name.replace(" ", "_")
    )

    try:
        uploaded_file.save(zip_path)

        if extract_dir.exists():
            import shutil
            shutil.rmtree(extract_dir)

        repo_analyzer.extract_repository(
            zip_path,
            extract_dir
        )

        repository_data = repo_analyzer.analyze_repository(
            extract_dir,
            team_name
        )

        existing_repo_path = Path(
            app.root_path
        ) / "test_repos"

        results = repo_analyzer.compare_repository_with_existing(
            repository_data,
            existing_repo_path
        )

        return render_template(
            "analyze_repo_results.html",
            team_name=team_name,
            files_scanned=repository_data["files_scanned"],
            functions_found=repository_data["functions_found"],
            results=results
        )

    except Exception as exc:
        return render_template(
            "analyze_repo.html",
            error=f"Repository analysis failed: {exc}"
        )

# ---------------------------------------------------------------------------
# Recommendation feedback
# ---------------------------------------------------------------------------

@app.route("/recommendation-feedback", methods=["POST"])
@login_required
def recommendation_feedback():

    decision = request.form.get("decision", "").strip().upper()

    if decision not in {"ACCEPT", "REJECT"}:
        return redirect(url_for("dashboard"))

    uploaded_file = request.form.get("uploaded_file", "")
    uploaded_function = request.form.get("uploaded_function", "")
    existing_team = request.form.get("existing_team", "")
    existing_file = request.form.get("existing_file", "")
    existing_function = request.form.get("existing_function", "")

    try:
        acceptance_score = float(
            request.form.get("acceptance_score", 0)
        )
    except ValueError:
        acceptance_score = 0

    db.save_feedback(
        DATABASE_FILE,
        session.get("username", ""),
        uploaded_file,
        uploaded_function,
        existing_team,
        existing_file,
        existing_function,
        acceptance_score,
        decision,
    )

    return redirect(url_for("check_file"))
if __name__ == "__main__":
    app.run(debug=True)