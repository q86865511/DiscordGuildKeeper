"""FastAPI application factory. Implemented in M1.

Builds the app, registers ``health`` (and later ``metrics``) routers, and runs
under uvicorn as an asyncio task alongside the Discord client. See
PROJECT_SPEC.md §4.2, §14.
"""
