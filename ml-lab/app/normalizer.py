import re

PATTERNS = [
    (re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"), "<IP>"),
    (re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F-]{27,}\b"), "<UUID>"),
    (re.compile(r"\b0x[0-9a-fA-F]+\b"), "<HEX>"),
    (re.compile(r"\b\d{4}-\d{2}-\d{2}T[^ ]+"), "<TIMESTAMP>"),
    (re.compile(r"\b\d+(?:\.\d+)?\b"), "<NUM>"),
]

def normalize_message(message: str) -> str:
    value = message.lower().strip()
    for pattern, token in PATTERNS:
        value = pattern.sub(token, value)
    return " ".join(value.split())
