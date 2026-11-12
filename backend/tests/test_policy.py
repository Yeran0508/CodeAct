from codeact.models import Action, CodeLanguage, RiskLevel
from codeact.policy import ActionPolicy


def test_read_only_bash_is_automatic() -> None:
    decision = ActionPolicy().evaluate(Action.execute("pwd && ls", CodeLanguage.BASH))
    assert decision.risk is RiskLevel.READ_ONLY
    assert not decision.requires_approval


def test_bash_deletion_requires_approval() -> None:
    decision = ActionPolicy().evaluate(Action.execute("rm -rf build", CodeLanguage.BASH))
    assert decision.risk is RiskLevel.HIGH_RISK
    assert decision.requires_approval
    assert "file deletion" in decision.reasons


def test_python_network_requires_approval() -> None:
    action = Action.execute("import socket\nsocket.socket()", CodeLanguage.PYTHON)
    decision = ActionPolicy().evaluate(action)
    assert decision.requires_approval
    assert decision.reasons == ("network access",)


def test_python_file_write_is_workspace_mutation() -> None:
    action = Action.execute("open('note.txt', 'w').write('x')", CodeLanguage.PYTHON)
    decision = ActionPolicy().evaluate(action)
    assert decision.risk is RiskLevel.WRITE
    assert not decision.requires_approval


def test_invalid_python_is_left_for_executor_to_report() -> None:
    decision = ActionPolicy().evaluate(Action.execute("if", CodeLanguage.PYTHON))
    assert decision.risk is RiskLevel.READ_ONLY
