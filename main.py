"""슈포트 프로젝트 git log를 분석해 팀원별/기간별 구현 요약과 블로그 초안을 생성한다.

사용 예:
    python main.py --periods config/periods.json
"""
import argparse
import json
import re
from pathlib import Path

from gitlog import ensure_repo, get_commits
from summarizer import summarize_author_period

DEFAULT_REPO_URL = "https://github.com/ssu-student-union/ssuport-frontend"


def sanitize(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|\s]+', "_", name).strip("_")


def load_periods(path: str) -> list[dict]:
    periods = json.loads(Path(path).read_text(encoding="utf-8"))
    for period in periods:
        if not {"name", "start", "end"} <= period.keys():
            raise ValueError(f"기간 설정에 name/start/end가 모두 필요합니다: {period}")
    return periods


def group_by_author(commits: list[dict]) -> dict[str, list[dict]]:
    by_author: dict[str, list[dict]] = {}
    for commit in commits:
        by_author.setdefault(commit["author"], []).append(commit)
    return by_author


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-url", default=DEFAULT_REPO_URL, help="clone할 저장소 URL")
    parser.add_argument("--repo-path", default="./repo", help="로컬에 clone될 경로")
    parser.add_argument("--periods", default="config/periods.json", help="기간 설정 JSON 파일")
    parser.add_argument("--output", default="./output", help="결과를 저장할 디렉터리")
    parser.add_argument("--branch", default=None, help="분석할 브랜치 (기본: HEAD)")
    parser.add_argument("--skip-pull", action="store_true", help="이미 clone된 저장소를 다시 pull하지 않음")
    args = parser.parse_args()

    if args.skip_pull and Path(args.repo_path, ".git").exists():
        repo_path = Path(args.repo_path)
    else:
        print(f"저장소 준비 중: {args.repo_url} -> {args.repo_path}")
        repo_path = ensure_repo(args.repo_url, args.repo_path)

    periods = load_periods(args.periods)
    commits = get_commits(repo_path, branch=args.branch)
    print(f"총 {len(commits)}개 커밋을 불러왔습니다.")

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    for period in periods:
        period_commits = [c for c in commits if period["start"] <= c["date"] <= period["end"]]
        by_author = group_by_author(period_commits)

        if not by_author:
            print(f"[{period['name']}] 해당 기간에 커밋이 없습니다.")
            continue

        for author, author_commits in sorted(by_author.items()):
            print(f"[{period['name']}] {author}: 커밋 {len(author_commits)}개 -> 요약 생성 중...")
            result = summarize_author_period(author, period["name"], author_commits)

            author_dir = output_dir / sanitize(author)
            author_dir.mkdir(parents=True, exist_ok=True)
            period_slug = sanitize(period["name"])

            (author_dir / f"{period_slug}_summary.md").write_text(result["summary"], encoding="utf-8")
            (author_dir / f"{period_slug}_blog_draft.md").write_text(result["blog_draft"], encoding="utf-8")

    print(f"완료. 결과는 {output_dir} 에 저장되었습니다.")


if __name__ == "__main__":
    main()
