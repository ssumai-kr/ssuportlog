"""슈포트 프로젝트 git log 분석 결과를 웹에서 조회하는 Flask 앱.

사용 예:
    python app.py
    -> http://localhost:5000 접속
"""
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, Response, jsonify, render_template, request

import db
from gitlog import ensure_repo, get_commits, get_diff
from summarizer import generate_blog_draft, generate_technical_analysis

MAX_DIFF_COMMITS = 5

load_dotenv()

DEFAULT_REPO_URL = "https://github.com/ssu-student-union/ssuport-frontend"
REPO_PATH = "./repo"
PERIODS_PATH = "config/periods.json"
AUTHORS_PATH = "config/authors.json"
BASIC_AUTH_USERNAME = os.environ.get("BASIC_AUTH_USERNAME")
BASIC_AUTH_PASSWORD = os.environ.get("BASIC_AUTH_PASSWORD")

app = Flask(__name__)
db.init_db()


@app.before_request
def require_basic_auth():
    """BASIC_AUTH_USERNAME/PASSWORD가 설정된 경우에만 로그인을 요구한다.
    로컬 개발 시(.env에 설정 안 함)에는 그냥 통과시켜 불편함이 없게 한다."""
    if not BASIC_AUTH_USERNAME or not BASIC_AUTH_PASSWORD:
        return None
    auth = request.authorization
    if not auth or auth.username != BASIC_AUTH_USERNAME or auth.password != BASIC_AUTH_PASSWORD:
        return Response(
            "Authentication required", 401,
            {"WWW-Authenticate": 'Basic realm="Login Required"'},
        )
    return None

_commits_cache: list[dict] | None = None


def load_periods() -> list[dict]:
    return json.loads(Path(PERIODS_PATH).read_text(encoding="utf-8"))


def load_author_alias_map() -> dict[str, str]:
    """config/authors.json의 {대표이름: [별칭, ...]}을 {별칭: 대표이름} 역방향 맵으로 변환."""
    path = Path(AUTHORS_PATH)
    if not path.exists():
        return {}
    canonical_groups = json.loads(path.read_text(encoding="utf-8"))
    alias_to_canonical = {}
    for canonical, aliases in canonical_groups.items():
        for alias in aliases:
            alias_to_canonical[alias] = canonical
    return alias_to_canonical


def get_all_commits() -> list[dict]:
    global _commits_cache
    if _commits_cache is None:
        repo_path = Path(REPO_PATH)
        if not (repo_path / ".git").exists():
            ensure_repo(DEFAULT_REPO_URL, REPO_PATH)
        commits = get_commits(repo_path)
        alias_map = load_author_alias_map()
        for c in commits:
            c["author"] = alias_map.get(c["author"], c["author"])
        _commits_cache = commits
    return _commits_cache


def commits_for_periods(commits: list[dict], periods: list[dict], period_names: list[str]) -> list[dict]:
    selected = [p for p in periods if p["name"] in period_names]
    result = [
        c for c in commits
        if any(p["start"] <= c["date"] <= p["end"] for p in selected)
    ]
    return sorted(result, key=lambda c: c["date"])


MAX_DIFF_COMMIT_SIZE = 400  # 변경량(insertions+deletions)이 이보다 큰 커밋은 보일러플레이트일 가능성이 높고
                            # diff 전체를 메모리에 올리는 비용도 커서 diff 후보에서 제외한다.


def attach_diffs(commits: list[dict], max_commits: int = MAX_DIFF_COMMITS) -> list[dict]:
    """핵심 구현 코드를 인용할 수 있도록, 작고 의미 있어 보이는 커밋 몇 개에만 실제 diff를 붙인다."""
    def score(c: dict) -> int:
        total = c["insertions"] + c["deletions"]
        if total > MAX_DIFF_COMMIT_SIZE:
            return -1
        keyword_bonus = 1000 if any(k in c["subject"].lower() for k in ("fix", "refactor", "버그", "수정", "개선")) else 0
        return keyword_bonus + total

    candidates = [c for c in commits if score(c) >= 0]
    chosen_hashes = {c["hash"] for c in sorted(candidates, key=score, reverse=True)[:max_commits]}
    for c in commits:
        if c["hash"] in chosen_hashes:
            c["diff"] = get_diff(Path(REPO_PATH), c["hash"])
    return commits


@app.route("/")
def index():
    try:
        periods = load_periods()
        commits = get_all_commits()
        authors = sorted({c["author"] for c in commits})
    except Exception as e:
        app.logger.exception("인덱스 페이지 로딩 실패")
        return f"<pre>{type(e).__name__}: {e}</pre>", 500
    return render_template("index.html", periods=periods, authors=authors)


@app.route("/api/commits")
def api_commits():
    commits = get_all_commits()
    return jsonify([
        {
            "hash": c["hash"],
            "date": c["date"],
            "author": c["author"],
            "subject": c["subject"],
        }
        for c in commits
    ])


@app.route("/api/analyze", methods=["POST"])
def api_analyze():
    data = request.get_json()
    author = data.get("author")
    period_names = data.get("periods") or []
    if not author or not period_names:
        return jsonify({"error": "author와 periods가 필요합니다."}), 400

    commits = commits_for_periods(get_all_commits(), load_periods(), period_names)
    target_commits = [c for c in commits if c["author"] == author]
    if not target_commits:
        return jsonify({"error": "해당 작성자/기간에 커밋이 없습니다."}), 404
    commit_hashes = [c["hash"] for c in target_commits]

    period_key = db.make_period_key(period_names)
    cached = db.get_cached(author, period_key, "summary")
    if cached:
        return jsonify({"cached": True, "commit_hashes": commit_hashes, **cached})

    target_commits = attach_diffs(target_commits)

    period_label = ", ".join(sorted(period_names))
    try:
        content = generate_technical_analysis(author, period_label, target_commits)
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 500
    db.save_cache(author, period_key, "summary", content, len(target_commits))
    return jsonify({
        "cached": False, "content": content, "commit_count": len(target_commits),
        "commit_hashes": commit_hashes,
    })


@app.route("/api/blog", methods=["POST"])
def api_blog():
    data = request.get_json()
    author = data.get("author")
    period_names = data.get("periods") or []
    if not author or not period_names:
        return jsonify({"error": "author와 periods가 필요합니다."}), 400

    commits = commits_for_periods(get_all_commits(), load_periods(), period_names)
    target_commits = [c for c in commits if c["author"] == author]
    commit_hashes = [c["hash"] for c in target_commits]

    period_key = db.make_period_key(period_names)
    cached = db.get_cached(author, period_key, "blog")
    if cached:
        return jsonify({"cached": True, "commit_hashes": commit_hashes, **cached})

    summary_cached = db.get_cached(author, period_key, "summary")
    if not summary_cached:
        return jsonify({"error": "먼저 기술 분석을 생성해주세요."}), 400

    period_label = ", ".join(sorted(period_names))
    try:
        content = generate_blog_draft(author, period_label, target_commits, summary_cached["content"])
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 500
    db.save_cache(author, period_key, "blog", content, len(target_commits))
    return jsonify({
        "cached": False, "content": content, "commit_count": len(target_commits),
        "commit_hashes": commit_hashes,
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "1") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug)
