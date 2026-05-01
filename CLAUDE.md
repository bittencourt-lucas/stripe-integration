# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

A Python library/utility for Stripe API integration. Managed with **Poetry** (Python 3.12+, Stripe SDK v15.x).

## Commands

```bash
poetry install          # Install dependencies
poetry run python ...   # Run a script within the venv
poetry add <pkg>        # Add a runtime dependency
poetry add --group dev <pkg>  # Add a dev dependency (e.g. pytest, ruff)
```

No test runner or linter is configured yet. When adding them, prefer **pytest** for tests and **ruff** for linting/formatting; configure both in `pyproject.toml`.

## Architecture

The project is currently a skeleton — only `pyproject.toml` and `poetry.lock` exist. No source code or module directory has been created yet.

When implementing, the expected layout is:
- `src/stripe_integration/` — main package
- `tests/` — test suite

The sole runtime dependency is the official [Stripe Python SDK](https://github.com/stripe/stripe-python) (`stripe>=15.1.0,<16.0.0`), which handles HTTP communication, retries, and type definitions internally.
