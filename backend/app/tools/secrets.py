"""Secret redaction. Applied to everything sent to an LLM and to stored evidence."""
from __future__ import annotations

import re

_PATTERNS = [
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{30,}\b"),
    re.compile(r"\bgsk_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
]
_ASSIGNMENT = re.compile(
    r"""(?ix)\b([A-Za-z0-9_]*(?:password|passwd|secret|token|api[_-]?key|private[_-]?key)[A-Za-z0-9_]*)
    (\s*[:=]\s*)(['"])[^'"\n]{6,}\3"""
)
REDACTED = "[REDACTED]"


def redact(text: str) -> str:
    """Replace anything that looks like a credential with a placeholder."""
    for pattern in _PATTERNS:
        text = pattern.sub(REDACTED, text)
    return _ASSIGNMENT.sub(lambda m: f"{m.group(1)}{m.group(2)}{m.group(3)}{REDACTED}{m.group(3)}", text)


def count_secrets(text: str) -> int:
    return sum(len(p.findall(text)) for p in _PATTERNS) + len(_ASSIGNMENT.findall(text))
