# Discord Butler Bot

A private friend-guild Discord butler bot — anime subscription notifications, ticket sale monitoring,
Gemini-powered Q&A, and channel summaries. Designed to run on Oracle Cloud ARM Always Free.

> **Single source of truth:** [`PROJECT_SPEC.md`](./PROJECT_SPEC.md). All implementation must follow it.
> **Current status:** M0 (project skeleton). See `PROJECT_SPEC.md` §23 for milestones.

## Quick start (local dev)

Prerequisites: Docker + Docker Compose, Python 3.12, [`uv`](https://docs.astral.sh/uv/).

```bash
cp .env.example .env       # then fill in DISCORD_TOKEN / GEMINI_API_KEY when ready
uv sync                    # install dependencies into .venv

# Run lint / typecheck / tests
uv run ruff format --check
uv run ruff check
uv run mypy src
uv run pytest

# Run the bot stack (postgres + redis + bot)
docker compose -f docker-compose.dev.yml up --build
```

At M0 the bot only initializes config + logging and idles — Discord lifecycle, health endpoints,
crawlers, and LLM are added in later milestones.

## Project layout

See `PROJECT_SPEC.md` §6 for the full tree. Top-level highlights:

```
src/butler/        Application source (package: butler)
  core/            Config, logging, db / redis clients, scheduler, version
  bot/             Discord client + cogs (M1+)
  api/             FastAPI health / metrics (M1+)
  crawlers/        animead / kktix / tixcraft (M3, M5)
  models/          SQLAlchemy ORM (M1+)
  repositories/    Data access (M1+)
  services/        Business logic (M3+)
tests/             pytest unit + integration
scripts/           entrypoint.sh, backup.sh
migrations/        Alembic (M1+)
.github/workflows/ CI + deploy (M2 adds deploy)
```

## License

MIT (see `pyproject.toml`).
