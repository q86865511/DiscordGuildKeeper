#!/usr/bin/env bash
# Container entrypoint for the bot service.
#
# Run pending Alembic migrations before launching the bot, so a fresh DB
# (or any new revision) is at HEAD by the time the app starts. Spec §15.2.
set -euo pipefail

alembic upgrade head

exec python -m butler.main
