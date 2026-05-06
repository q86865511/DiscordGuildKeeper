"""Slash-command cogs. Cogs MUST stay thin — no SQL, no direct httpx, no LLM calls.

Business logic lives in ``services/``; data access in ``repositories/``;
external HTTP in ``crawlers/`` and ``services/llm.py``.
"""
