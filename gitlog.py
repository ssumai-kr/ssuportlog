"""git 저장소를 clone/pull하고 커밋 로그를 구조화된 데이터로 추출한다."""
import re
import subprocess
from pathlib import Path

FIELD_SEP = "\x1f"
RECORD_SEP = "\x1e"
HASH_RE = re.compile(r"^[0-9a-f]{40}$")
SHORTSTAT_RE = re.compile(
    r"(\d+) files? changed(?:, (\d+) insertions?\(\+\))?(?:, (\d+) deletions?\(-\))?"
)


def ensure_repo(repo_url: str, repo_path: str) -> Path:
    """repo_path에 이미 clone되어 있으면 pull, 없으면 clone한다."""
    path = Path(repo_path)
    if (path / ".git").exists():
        subprocess.run(["git", "-C", str(path), "pull"], check=True)
    else:
        path.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "clone", repo_url, str(path)], check=True)
    return path


def _parse_metadata(repo_path: Path, ref: str) -> list[dict]:
    fmt = FIELD_SEP.join(["%H", "%an", "%ae", "%ad", "%s", "%b"]) + RECORD_SEP
    result = subprocess.run(
        ["git", "-C", str(repo_path), "log", ref, f"--pretty=format:{fmt}", "--date=short"],
        check=True, capture_output=True, text=True, encoding="utf-8",
    )
    commits = []
    for record in result.stdout.split(RECORD_SEP):
        record = record.strip("\n")
        if not record:
            continue
        fields = record.split(FIELD_SEP)
        if len(fields) < 6:
            continue
        commit_hash, author, email, date, subject, body = fields[:6]
        commits.append({
            "hash": commit_hash,
            "author": author.strip(),
            "email": email.strip(),
            "date": date.strip(),
            "subject": subject.strip(),
            "body": body.strip(),
        })
    return commits


def _parse_shortstats(repo_path: Path, ref: str) -> dict[str, tuple[int, int, int]]:
    result = subprocess.run(
        ["git", "-C", str(repo_path), "log", ref, "--pretty=format:%H", "--shortstat"],
        check=True, capture_output=True, text=True, encoding="utf-8",
    )
    stats: dict[str, tuple[int, int, int]] = {}
    current_hash = None
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        if HASH_RE.match(line):
            current_hash = line
            stats[current_hash] = (0, 0, 0)
            continue
        m = SHORTSTAT_RE.search(line)
        if m and current_hash is not None:
            files = int(m.group(1) or 0)
            insertions = int(m.group(2) or 0)
            deletions = int(m.group(3) or 0)
            stats[current_hash] = (files, insertions, deletions)
    return stats


def get_diff(repo_path: Path, commit_hash: str, max_chars: int = 2500) -> str:
    """단일 커밋의 unified diff를 가져온다 (커밋 메시지 제외, 코드 변경분만)."""
    result = subprocess.run(
        ["git", "-C", str(repo_path), "show", "--no-color", "--unified=2", "--pretty=format:", commit_hash],
        check=True, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    diff = result.stdout.strip()
    if len(diff) > max_chars:
        diff = diff[:max_chars] + "\n... (이하 생략)"
    return diff


def get_commits(repo_path: Path, branch: str | None = None) -> list[dict]:
    """저장소의 커밋 목록을 author/date/message/변경통계가 포함된 dict 리스트로 반환한다."""
    ref = branch or "HEAD"
    commits = _parse_metadata(repo_path, ref)
    stats = _parse_shortstats(repo_path, ref)
    for commit in commits:
        files_changed, insertions, deletions = stats.get(commit["hash"], (0, 0, 0))
        commit["files_changed"] = files_changed
        commit["insertions"] = insertions
        commit["deletions"] = deletions
    return commits
