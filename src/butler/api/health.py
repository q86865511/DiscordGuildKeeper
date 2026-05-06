"""Health, readiness, and version endpoints. Implemented in M1.

  - ``GET /healthz``  — process liveness (200 if reachable).
  - ``GET /readyz``   — DB / Redis / Discord readiness aggregate.
  - ``GET /version``  — app version + git sha + build time.

See PROJECT_SPEC.md §14.
"""
