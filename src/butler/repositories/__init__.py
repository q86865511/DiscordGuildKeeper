"""Data-access layer. Repositories are the only place that constructs SQL queries.

Cogs and services depend on repository methods, never on SQLAlchemy directly.
See PROJECT_SPEC.md §6, §25.
"""
