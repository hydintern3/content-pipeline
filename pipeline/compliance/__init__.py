"""Content compliance checking package.

Uses LLM-based semantic checking against platform content guidelines (doc/),
supplemented by regex pre-checks for structural violations like phone numbers
and contact information.
"""

from __future__ import annotations

from .checker import check_articles, check_text  # noqa: F401
