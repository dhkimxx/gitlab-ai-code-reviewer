from typing import List, TypedDict

from src.shared.types import ChatMessageDict


class RefactorSuggestionFile(TypedDict):
    path: str
    content: str
    truncated: bool


DEFAULT_REFACTOR_SUGGESTION_SYSTEM_INSTRUCTION = """
당신은 시니어 테크 리드이며, 리팩토링 제안("코드를 이전보다 조금 더 깨끗하게 남긴다") 관점의 리팩토링 리뷰어입니다.

목표:
- 아래 제공된 "파일 전체 코드"를 기준으로, 유지보수성과 안전성을 높이는 실질적인 개선안을 제시합니다.
- diff 중심 리뷰가 아니라, 파일 단위의 구조/가독성/복잡도 개선에 집중합니다.

중요 규칙:
- 제공된 파일 내용만 근거로 답변하십시오.
- 추측하지 말고, 확인 가능한 근거를 기준으로 제안하십시오.
- 사소한 취향 논쟁은 줄이고, 효과 대비 비용이 좋은 제안부터 우선순위를 매기십시오.
- 치명적 버그 탐지보다 "점진적 개선(리팩토링 기회)"에 집중하십시오.

출력 형식:
### 1. Top Refactoring Opportunities
- 최대 5개, 중요도 순으로 제시
- 각 항목은 [파일경로]로 시작

### 2. File-by-File Refactoring Suggestions
- 파일별로 1~3개 개선안
- 각 개선안에 "왜 지금 개선하면 좋은지"를 한 문장 포함

### 3. Quick Wins (<= 30 minutes)
- 즉시 적용 가능한 작은 개선 항목

### 4. Suggested Refactoring Plan
- 이번 MR 이후 backlog로 넘길 중기 개선 과제 제시
"""


def generate_refactor_suggestion_prompt(files: List[RefactorSuggestionFile]) -> List[ChatMessageDict]:
    file_sections: List[str] = []
    for file in files:
        truncate_note = " (truncated)" if file.get("truncated") else ""
        file_sections.append(
            "\n".join(
                [
                    f"## FILE: {file['path']}{truncate_note}",
                    "```",
                    file["content"],
                    "```",
                ]
            )
        )

    user_prompt = (
        "다음은 이번 MR에서 변경된 코드 파일의 전체 본문입니다.\n"
        "리팩토링 제안 관점에서 리팩토링/정리 제안을 작성하세요.\n\n"
        + "\n\n".join(file_sections)
    )

    return [
        {"role": "system", "content": DEFAULT_REFACTOR_SUGGESTION_SYSTEM_INSTRUCTION},
        {"role": "user", "content": user_prompt},
    ]
