from src.infra.repositories.refactor_suggestion_state_repo import RefactorSuggestionStateRepository


def test_try_claim_allows_only_once(tmp_path) -> None:
    repo = RefactorSuggestionStateRepository(str(tmp_path / "refactor_suggestion_state_1.db"))

    assert repo.try_claim(1, 10) is True
    assert repo.try_claim(1, 10) is False
    assert repo.get_status(1, 10) == "queued"


def test_release_only_removes_queued(tmp_path) -> None:
    repo = RefactorSuggestionStateRepository(str(tmp_path / "refactor_suggestion_state_2.db"))

    assert repo.try_claim(2, 20) is True
    repo.release_claim(2, 20)
    assert repo.get_status(2, 20) is None

    assert repo.try_claim(2, 20) is True
    repo.mark_completed(2, 20)
    repo.release_claim(2, 20)
    assert repo.get_status(2, 20) == "completed"
