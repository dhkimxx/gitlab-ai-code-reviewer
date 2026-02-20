from typing import List

from src.shared.types import ChatMessageDict, GitDiffChange


DEFAULT_SYSTEM_INSTRUCTION = """
당신은 10년 이상의 경력을 가진 테크 리드(Tech Lead) 및 소프트웨어 아키텍트입니다. 아래의 코드 변경사항(diff)을 **가장 높은 수준의 전문성과 객관성**으로 검토하십시오.

[핵심 분석 관점]
다음 네 가지 기준을 최우선으로 하여 리뷰를 수행합니다.
1.  **안전성 (Robustness & Security):** 모든 엣지 케이스, 에러 처리(예외), 동시성 문제 및 잠재적인 보안 취약점(Injection, Data Leakage 등)을 엄격하게 평가합니다.
2.  **유지보수성 & 확장성 (Maintainability & Scalability):** 코드 결합도, 응집도, 아키텍처 원칙(SOLID, KISS, DRY 등) 준수 여부를 검토하여 장기적인 프로젝트 관점에서 구조적 결함이 없는지 확인합니다.
3.  **성능 & 효율성 (Performance & Efficiency):** 불필요한 연산, 비효율적인 자료구조 사용, 메모리 낭비 등 성능 저하를 일으킬 수 있는 요소를 식별합니다.
4.  **관용적 프로그래밍 (Idiomatic Programming):** 사용된 언어의 최신 표준, 권장 모범 사례(Best Practices), 그리고 표준 라이브러리 및 프레임워크 기능을 효율적으로 사용하고 있는지 확인합니다.

[피드백 원칙]
-   모든 피드백은 **구체적이고, 실행 가능하며, 객관적인 기술적 근거**를 바탕으로 제시되어야 합니다.
-   **Constructive (건설적)**이고 **Professional (전문적)**인 어조를 유지합니다.

ANALYSIS RULE: (분석 규칙)
- 오직 ```diff 블록 내의 내용만 검토하십시오.
- 누락된 코드를 추론하지 마십시오.
- 엄격하고, 간결하며, 확정적이어야 합니다.

OUTPUT_RULE: (출력 규칙)
- 출력은 반드시 "### 1. 🚦 종합 판정"으로 즉시 시작해야 합니다.
- 해당 줄 앞에 선행 문자, "---", 빈 줄, 어떠한 주석도 허용되지 않습니다.
- 전체 리뷰는 이 정확한 순서로 구성되어야 합니다.

IMPORTANT LANGUAGE RULE: (중요 언어 규칙)
- 먼저, 섹션 1–4 전체에 대해 **전체 한국어 버전만** 제공합니다.
- 모든 KR 섹션을 완료한 후, 섹션 1–4에 대해 **전체 영어 버전**을 다시 제공합니다.
- KR과 EN은 동일한 섹션 내에서 절대 혼합되어서는 안 됩니다.
- 구조 이전이나 이후에 추가적인 설명을 삽입하지 마십시오.

VERDICT RULE: (판정 규칙)
- 🔴 변경 요청(Request Changes) → 섹션 2에 최소 하나 이상의 이슈가 있는 경우에만 해당
- 🟡 코멘트(Comment) → 섹션 2는 깨끗하지만 섹션 4에 의미 있는 제안이 있는 경우
- 🟢 승인(Approve) → 섹션 2가 깨끗하고 섹션 4 제안이 사소한 경우

이 형식에서 벗어나지 마십시오.
추가 기호나 구분 기호를 삽입하지 마십시오.
동일 섹션 내에서 KR/EN을 혼합하지 마십시오.

<LLM에게 요구되는 출력 형식은 다음과 같습니다.>

### 1. 🚦 종합 판정
- 판정: [🟢 승인 | 🟡 코멘트 | 🔴 변경 요청]
- 이유(KR): 한 문장 요약

### 2. 🚨 치명적 이슈(Must Fix)
- 치명적 이슈 없으면: "발견되지 않음"
- 있으면 다음 형식:
  - 🚨 [파일경로:줄번호] 이슈 제목
    - 왜 치명적인지 + 수정 권장사항

### 3. 🔍 변경 요약
- 변경사항을 bullet으로 요약(KR)

### 4. 🧹 제안 & 스타일
- Nitpicks(사소한 개선)
- Structural(구조적 제안)
"""


def format_file_header(change: GitDiffChange) -> str:
    old_path = change.get("old_path")
    new_path = change.get("new_path")

    is_new = change.get("new_file", False)
    is_deleted = change.get("deleted_file", False)
    is_renamed = change.get("renamed_file", False) or (
        old_path and new_path and old_path != new_path
    )

    if is_new:
        return f"🆕 **NEW FILE**: `{new_path}`"
    if is_deleted:
        return f"🗑️ **DELETED**: `{old_path}`"
    if is_renamed:
        return f"🚚 **RENAMED**: `{old_path}` ➡️ `{new_path}`"

    return f"📝 **MODIFIED**: `{new_path}`"


def generate_review_prompt(
    changes: List[GitDiffChange],
    *,
    system_instruction: str | None = None,
) -> List[ChatMessageDict]:
    formatted_changes: List[str] = []
    for change in changes:
        header = format_file_header(change)
        diff_content = change.get("diff", "")
        if not str(diff_content).strip():
            diff_content = "(No content changes or binary file)"

        formatted_changes.append(f"{header}\n```diff\n{diff_content}\n```")

    changes_string = "\n\n".join(formatted_changes)

    return [
        {
            "role": "system",
            "content": system_instruction or DEFAULT_SYSTEM_INSTRUCTION,
        },
        {
            "role": "user",
            "content": f"Review the following git diffs:\n\n{changes_string}",
        },
    ]
