"""redis-py asyncio client. Implemented in M1.

Used for rate limiting (``/ask``, ``/summary``), scheduler locks, and short-lived
caches. See PROJECT_SPEC.md §9.
"""
