from __future__ import annotations

import ast
import re

from codeact.models import Action, CodeLanguage, PolicyDecision, RiskLevel

_BASH_HIGH_RISK = (
    (re.compile(r"(^|[;&|]\s*)rm\s+(-[^\n;]*\s+)*[^\n;]+"), "file deletion"),
    (re.compile(r"\bgit\s+push\b"), "remote repository mutation"),
    (re.compile(r"\b(curl|wget)\b"), "network access"),
    (re.compile(r"\b(sudo|chmod|chown)\b"), "privilege or permission change"),
    (re.compile(r"\bdocker\s+(run|exec|build|push|rm)\b"), "Docker daemon access"),
)
_BASH_WRITE = re.compile(r"(^|\s)(touch|mkdir|mv|cp|sed\s+-i)\b|>{1,2}")
_PYTHON_HIGH_RISK_CALLS = {
    "os.remove": "file deletion",
    "os.unlink": "file deletion",
    "os.rmdir": "directory deletion",
    "shutil.rmtree": "recursive deletion",
    "requests.get": "network access",
    "requests.post": "network access",
    "urllib.request.urlopen": "network access",
    "socket.socket": "network access",
    "subprocess.run": "nested process execution",
    "subprocess.Popen": "nested process execution",
}
_PYTHON_WRITE_CALLS = {"open", "Path.write_text", "Path.write_bytes", "os.mkdir", "os.makedirs"}


def _call_name(node: ast.Call) -> str:
    parts: list[str] = []
    current: ast.expr = node.func
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
    return ".".join(reversed(parts))


class ActionPolicy:
    """Classify actions before execution; unknown or dangerous behavior needs approval."""

    def evaluate(self, action: Action) -> PolicyDecision:
        if action.language is CodeLanguage.BASH:
            return self._evaluate_bash(action.code)
        return self._evaluate_python(action.code)

    def _evaluate_bash(self, code: str) -> PolicyDecision:
        reasons = tuple(reason for pattern, reason in _BASH_HIGH_RISK if pattern.search(code))
        if reasons:
            return PolicyDecision(RiskLevel.HIGH_RISK, True, reasons)
        if _BASH_WRITE.search(code):
            return PolicyDecision(RiskLevel.WRITE, False, ("workspace mutation",))
        return PolicyDecision(RiskLevel.READ_ONLY, False)

    def _evaluate_python(self, code: str) -> PolicyDecision:
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return PolicyDecision(RiskLevel.READ_ONLY, False)

        high_risk: set[str] = set()
        writes = False
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = _call_name(node)
            if name in _PYTHON_HIGH_RISK_CALLS:
                high_risk.add(_PYTHON_HIGH_RISK_CALLS[name])
            if name in _PYTHON_WRITE_CALLS:
                if name == "open" and len(node.args) > 1:
                    mode = node.args[1]
                    if isinstance(mode, ast.Constant) and isinstance(mode.value, str):
                        writes = writes or any(flag in mode.value for flag in "wax+")
                elif name != "open":
                    writes = True
        if high_risk:
            return PolicyDecision(RiskLevel.HIGH_RISK, True, tuple(sorted(high_risk)))
        if writes:
            return PolicyDecision(RiskLevel.WRITE, False, ("workspace mutation",))
        return PolicyDecision(RiskLevel.READ_ONLY, False)
