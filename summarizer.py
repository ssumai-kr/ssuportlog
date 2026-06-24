"""Claude API를 사용해 커밋 목록(+ 일부 실제 diff)을 기승전결 구조의 기술 분석과 블로그 초안으로 변환한다."""
import os
import textwrap

from anthropic import Anthropic

MODEL = "claude-haiku-4-5"

_client: Anthropic | None = None

ANALYSIS_INSTRUCTIONS = """당신은 '슈포트' 프로젝트의 기술 회고를 정리하는 어시스턴트입니다.
사용자가 작성자/기간과 git 커밋 목록(일부 커밋은 실제 diff 포함)을 줄 것입니다. 커밋과 diff에서 확인되는 사실에만 근거하고, 주어지지 않은 코드나 내용을 추측해서 만들어내지 마세요.

요즘 포트폴리오/기술 면접 답변 트렌드에 맞춰, 기승전결(起承轉結) 구조로 다음 4개 섹션을 마크다운 헤딩으로 구분해서 작성하세요.

## 기 - 배경 및 과제
이 기간에 어떤 배경/목표로 어떤 작업을 맡게 되었는지 (커밋 흐름에서 유추 가능한 범위까지만)

## 승 - 구현 내용
실제로 구현/수정한 기능을 기술적으로 정리. 기능 개발 / 버그 수정 / 리팩토링 등으로 묶고, 어떤 기술적 선택을 했는지 드러나게 작성

## 전 - 페인포인트와 핵심 구현
- 어떤 기술적 어려움/시행착오가 있었는지 구체적으로 서술 (인터뷰에서 "어떤 문제가 있었고 어떻게 해결했나요"에 바로 답할 수 있는 수준)
- diff가 제공된 커밋 중 그 문제 해결의 핵심이 되는 변경 부분을 ```diff 코드 블록으로 인용하고, 무엇이 왜 어떻게 바뀌었는지 설명
- 해당 문제와 관련된 diff가 없으면 코드 인용 없이 설명만 작성 (diff를 지어내지 말 것)

## 결 - 개선 효과와 배운 점
- 위 핵심 구현을 통해 구체적으로 무엇이 개선되었는지 (커밋에서 확인되는 사실 기반: 버그 해결, 성능, 코드 구조, UX 등)
- 기술적으로 배운 점"""

BLOG_INSTRUCTIONS = """당신은 개발 블로그 초안을 작성하는 어시스턴트입니다.
사용자가 작성자/기간, git 커밋 목록, 그리고 이미 정리된 기승전결 기술 분석(핵심 코드 인용 포함)을 줄 것입니다.
이를 바탕으로 작성자 본인이 블로그에 그대로 올릴 수 있는 1인칭 개발 회고 글 초안을 한국어로 작성하세요.

작성 가이드:
- 1인칭, 자연스러운 글투
- 어떤 문제를 마주쳤고 어떻게 해결했는지가 드러나야 함 (기술 분석에 인용된 핵심 코드가 있다면 자연스럽게 포함)
- 배운 점이나 느낀 점으로 마무리
- 5~10문단 정도, 마크다운 형식, 제목(# )으로 시작"""


def get_client() -> Anthropic:
    global _client
    if _client is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY 환경변수가 설정되어 있지 않습니다.")
        _client = Anthropic(api_key=api_key)
    return _client


def format_commits_for_prompt(commits: list[dict]) -> str:
    lines = []
    for c in commits:
        message = c["subject"]
        if c["body"]:
            message += f"\n  {c['body'].strip()}"
        stat = f"(+{c['insertions']}/-{c['deletions']}, 파일 {c['files_changed']}개)"
        lines.append(f"- [{c['date']}] {message} {stat}")
        if c.get("diff"):
            lines.append("  실제 diff:")
            lines.append("  ```diff")
            lines.append(textwrap.indent(c["diff"], "  "))
            lines.append("  ```")
    return "\n".join(lines)


def _create(system_text: str, user_text: str) -> str:
    response = get_client().messages.create(
        model=MODEL,
        max_tokens=4096,
        system=[{"type": "text", "text": system_text, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user_text}],
    )
    return "".join(block.text for block in response.content if block.type == "text")


def generate_technical_analysis(author: str, period_label: str, commits: list[dict]) -> str:
    commit_log = format_commits_for_prompt(commits)
    user_text = f"작성자: {author}\n기간: {period_label}\n\n커밋 목록:\n{commit_log}"
    return _create(ANALYSIS_INSTRUCTIONS, user_text)


def generate_blog_draft(author: str, period_label: str, commits: list[dict], technical_analysis: str) -> str:
    commit_log = format_commits_for_prompt(commits)
    user_text = (
        f"작성자: {author}\n기간: {period_label}\n\n"
        f"[커밋 목록]\n{commit_log}\n\n[기술 분석]\n{technical_analysis}"
    )
    return _create(BLOG_INSTRUCTIONS, user_text)
