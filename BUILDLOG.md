# BUILDLOG.md — Append-only session log. One entry per agent session.

Format:
## [date] | [agent: Claude Code / Codex / Gemini / Perplexity] | [branch]
- Task attempted:
- Files touched:
- Tests run and result:
- Stage gate progress:
- Handover note:

## 2026-07-10 | agent: Gemini | branch: stage-0-foundation
- Task attempted: Stage 0 scope freeze and synthetic company factory. Set up Git repository, Docker Compose, clean Python/Django environment, pytest config, CI config, decision logs D-004/005/006, exclusions list, deterministic synthetic company factory generating CareCo, ConsultCo, and TradeCo fixtures, and a fixture validation test suite.
- Files touched:
  - Modify: [DECISIONS.md](file:///c:/Users/kfrem/OneDrive/CLIENTS/CLOSE%20COMPANIES/KAFS%20LTD/KAFS%20AUTOMATION/Coaching%20Business/Apps%20Dev/FULL%20ACCOUNTS%20DEPT/DECISIONS.md), [STATE.md](file:///c:/Users/kfrem/OneDrive/CLIENTS/CLOSE%20COMPANIES/KAFS%20LTD/KAFS%20AUTOMATION/Coaching%20Business/Apps%20Dev/FULL%20ACCOUNTS%20DEPT/STATE.md), [BUILDLOG.md](file:///c:/Users/kfrem/OneDrive/CLIENTS/CLOSE%20COMPANIES/KAFS%20LTD/KAFS%20AUTOMATION/Coaching%20Business/Apps%20Dev/FULL%20ACCOUNTS%20DEPT/BUILDLOG.md)
  - Create: [.dockerignore](file:///c:/Users/kfrem/OneDrive/CLIENTS/CLOSE%20COMPANIES/KAFS%20LTD/KAFS%20AUTOMATION/Coaching%20Business/Apps%20Dev/FULL%20ACCOUNTS%20DEPT/.dockerignore), [.env.example](file:///c:/Users/kfrem/OneDrive/CLIENTS/CLOSE%20COMPANIES/KAFS%20LTD/KAFS%20AUTOMATION/Coaching%20Business/Apps%20Dev/FULL%20ACCOUNTS%20DEPT/.env.example), [.github/workflows/ci.yml](file:///c:/Users/kfrem/OneDrive/CLIENTS/CLOSE%20COMPANIES/KAFS%20LTD/KAFS%20AUTOMATION/Coaching%20Business/Apps%20Dev/FULL%20ACCOUNTS%20DEPT/.github/workflows/ci.yml), [.gitignore](file:///c:/Users/kfrem/OneDrive/CLIENTS/CLOSE%20COMPANIES/KAFS%20LTD/KAFS%20AUTOMATION/Coaching%20Business/Apps%20Dev/FULL%20ACCOUNTS%20DEPT/.gitignore), [Dockerfile](file:///c:/Users/kfrem/OneDrive/CLIENTS/CLOSE%20COMPANIES/KAFS%20LTD/KAFS%20AUTOMATION/Coaching%20Business/Apps%20Dev/FULL%20ACCOUNTS%20DEPT/Dockerfile), [EXCLUSIONS.md](file:///c:/Users/kfrem/OneDrive/CLIENTS/CLOSE%20COMPANIES/KAFS%20LTD/KAFS%20AUTOMATION/Coaching%20Business/Apps%20Dev/FULL%20ACCOUNTS%20DEPT/EXCLUSIONS.md), [docker-compose.yml](file:///c:/Users/kfrem/OneDrive/CLIENTS/CLOSE%20COMPANIES/KAFS%20LTD/KAFS%20AUTOMATION/Coaching%20Business/Apps%20Dev/FULL%20ACCOUNTS%20DEPT/docker-compose.yml), [pytest.ini](file:///c:/Users/kfrem/OneDrive/CLIENTS/CLOSE%20COMPANIES/KAFS%20LTD/KAFS%20AUTOMATION/Coaching%20Business/Apps%20Dev/FULL%20ACCOUNTS%20DEPT/pytest.ini), [requirements.txt](file:///c:/Users/kfrem/OneDrive/CLIENTS/CLOSE%20COMPANIES/KAFS%20LTD/KAFS%20AUTOMATION/Coaching%20Business/Apps%20Dev/FULL%20ACCOUNTS%20DEPT/requirements.txt), [manage.py](file:///c:/Users/kfrem/OneDrive/CLIENTS/CLOSE%20COMPANIES/KAFS%20LTD/KAFS%20AUTOMATION/Coaching%20Business/Apps%20Dev/FULL%20ACCOUNTS%20DEPT/manage.py), `ledgerhouse/*` settings/urls/wsgi/asgi/init, `accounting/*` apps/init/fixtures/factory/generator/tests/test_fixtures.
- Tests run and result: Run `.venv\Scripts\pytest` locally (8 passed) and `docker compose run --rm web pytest` inside container (8 passed). Verification succeeds for reproducibility, journal double-entry balance, trial balance zero-sum, VAT control reconciliations, aging ledgers, and exclusion checks.
- Stage-gate status: Stage 0 complete and verified. All gate checklists met.
- Commit hash: a596978
- Security/data implications: No real user/personal information used. Access and data isolation controls established in D-004/005/006.
- Known limitations or blockers: None.
- Exact next task for the next agent: Proceed to Stage 1: Accounting Kernel (PLAN.md Section 6.2, Wk 4–8). Implement the core Django database models for charts, journals, periods, reversals, audit events, tenant relationships, and PostgreSQL row-level security isolation.
