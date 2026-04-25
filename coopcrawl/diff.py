from __future__ import annotations

import difflib


def make_diff(last: str, current: str) -> str:
    """Unified diff between two strings; empty when identical."""
    return "".join(
        difflib.unified_diff(
            last.splitlines(keepends=True),
            current.splitlines(keepends=True),
            n=3,
        )
    )
