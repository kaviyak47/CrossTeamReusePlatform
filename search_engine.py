"""
search_engine.py

A small, dependency-free search engine for the "Search existing work" page
(Phase 2). It uses TF-IDF (term frequency x inverse document frequency)
with cosine similarity, written in plain Python so no extra packages or
paid APIs are needed.

How it works, in short:
1. Every recommendation becomes one small "document" made of words.
   Words from function names count more than words from code evidence.
2. snake_case / camelCase names and file paths are split into words, so
   calculate_net_salary becomes: calculate, net, salary.
3. The search query is split the same way.
4. Each document is scored against the query. Rarer words count more
   (that is the "IDF" part). Documents with no shared words are dropped.

It never changes any data. It only reads what app.py already loaded.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any

# Very common words that carry no meaning for a search.
STOPWORDS = {
    "a", "an", "the", "of", "for", "to", "and", "or", "in", "on", "with", "from",
    "is", "are", "be", "it", "this", "that", "my", "me", "i", "we", "our", "need",
    "want", "how", "do", "does", "not", "any", "some", "something", "module", "code",
}

# Groups of words that mean nearly the same thing in a software project.
# A query word also searches its group, but with a lower weight.
SYNONYM_GROUPS = [
    {"salary", "pay", "wage", "payroll", "earnings"},
    {"login", "signin", "auth", "authentication", "authenticate", "logon"},
    {"upload", "uploader", "attachment"},
]
SYNONYM_WEIGHT = 0.5

# How important each kind of text is (bigger = matters more).
WEIGHT_FUNCTION = 3.0
WEIGHT_FILE_NAME = 2.0
WEIGHT_PATH_AND_TEAM = 1.5
WEIGHT_TEXT = 1.0        # recommendation text and reasons
WEIGHT_EVIDENCE = 0.5    # code shown in the diff


def _stem(word: str) -> str:
    """Very light plural handling: salaries -> salary, teams -> team."""
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def raw_words(text: str | None) -> list[str]:
    """Split text into lowercase words. Handles snake_case, camelCase, paths."""
    if not text:
        return []
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", str(text))  # calculateNet -> calculate Net
    return re.findall(r"[a-z0-9]+", text.lower())              # "_", "/", "." all split words


def words(text: str | None) -> list[str]:
    """Words with stopwords removed and plurals simplified."""
    return [_stem(w) for w in raw_words(text) if w not in STOPWORDS]


def joined_pairs(text: str | None) -> list[str]:
    """
    Join neighbouring words: "team_a" -> "teama". This lets the query
    "team a" find Team A, even though "a" alone is too short to search for.
    """
    parts = raw_words(text)
    return [parts[i] + parts[i + 1] for i in range(len(parts) - 1)]


def _file_name(path: str) -> str:
    return re.split(r"[\\/]", path)[-1] if path else ""


def build_document(rec: dict[str, Any]) -> Counter:
    """Turn one prepared recommendation into weighted word counts."""
    doc: Counter = Counter()

    def add(text: str | None, weight: float, pairs: bool = False) -> None:
        for w in words(text):
            doc[w] += weight
        if pairs:
            for p in joined_pairs(text):
                doc[p] += weight

    for side in (rec["source"], rec["matched"]):
        add(side["function"], WEIGHT_FUNCTION)
        add(_file_name(side["file"]), WEIGHT_FILE_NAME)
        add(side["file"], WEIGHT_PATH_AND_TEAM)
        add(side["team"], WEIGHT_PATH_AND_TEAM, pairs=True)
        # Team folder names inside paths, e.g. test_repos/team_a/...
        for folder in re.split(r"[\\/]", side["file"])[:-1]:
            for p in joined_pairs(folder):
                doc[p] += WEIGHT_PATH_AND_TEAM

    add(rec.get("recommendation"), WEIGHT_TEXT)
    for reason in rec.get("reasons", []):
        add(reason, WEIGHT_TEXT)
    add(rec.get("match_type"), WEIGHT_TEXT)
    add(" ".join(row["text"] for row in rec.get("diff", [])), WEIGHT_EVIDENCE)
    return doc


def build_query(query: str) -> tuple[dict[str, float], set[str]]:
    """
    Returns (term -> weight, the set of terms the user actually typed).
    Typed words get weight 1.0; synonyms get a lower weight.
    """
    typed = set(words(query)) | set(joined_pairs(query))
    terms: dict[str, float] = {t: 1.0 for t in typed}
    for group in SYNONYM_GROUPS:
        if typed & group:
            for synonym in group - typed:
                terms.setdefault(synonym, SYNONYM_WEIGHT)
    return terms, typed


def search(query: str, recommendations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Return matching recommendations, best match first.
    Each item is: {"rec": <recommendation>, "score": float, "matched_terms": [..]}
    """
    terms, typed = build_query(query)
    if not terms or not recommendations:
        return []

    docs = [build_document(r) for r in recommendations]
    pair_words = set(joined_pairs(query)) - set(words(query))

    # Document frequency: in how many documents does each word appear?
    doc_freq: Counter = Counter()
    for d in docs:
        doc_freq.update(d.keys())
    n = len(docs)

    def idf(term: str) -> float:
        return math.log((1 + n) / (1 + doc_freq.get(term, 0))) + 1

    query_vec = {t: w * idf(t) for t, w in terms.items()}
    query_norm = math.sqrt(sum(v * v for v in query_vec.values()))

    results = []
    for rec, doc in zip(recommendations, docs):
        doc_vec = {t: (1 + math.log(c)) * idf(t) for t, c in doc.items() if c > 0}
        shared = [t for t in query_vec if t in doc_vec]
        if not shared:
            continue  # nothing in common -> not a match
        dot = sum(query_vec[t] * doc_vec[t] for t in shared)
        doc_norm = math.sqrt(sum(v * v for v in doc_vec.values()))
        score = dot / (query_norm * doc_norm)
        # Show typed words first, then any synonyms that matched.
        # (Joined pairs like "teama" are internal helpers, so they are not displayed.)
        shared = [t for t in shared if t not in pair_words]
        matched = sorted(t for t in shared if t in typed) + sorted(t for t in shared if t not in typed)
        results.append({"rec": rec, "score": score, "matched_terms": matched})

    # Best text match first; ties go to higher similarity.
    results.sort(key=lambda r: (-r["score"], -r["rec"]["similarity"]))
    return results
