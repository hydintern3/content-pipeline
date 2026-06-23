"""Data models for compliance checking."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RegexRule:
    """A regex-based compliance rule for structural pattern matching."""

    id: str
    pattern: str  # regex pattern
    category: str
    level: str  # "high" | "medium" | "low"
    suggestion: str
    description: str = ""
    platforms: frozenset[str] | None = None  # None = all platforms
