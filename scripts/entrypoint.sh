#!/usr/bin/env bash
# Container entrypoint for the bot service.
#
# M0: just exec the bot — no migrations exist yet.
# M1+: prepend `alembic upgrade head` once the first migration lands.
set -euo pipefail

exec python -m butler.main
