"""SQLAlchemy 2.x async engine + session factory. Implemented in M1.

Will provide an ``AsyncEngine`` keyed off ``Settings.database_url`` plus a
session-scoped factory for repository code. See PROJECT_SPEC.md §5, §8.
"""
