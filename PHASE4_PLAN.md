# PHASE4_PLAN.md — Productization & Go-Live (engine → usable app)

Status of the platform at the start of this phase: the accounting engine is
complete, audited, hardened and CI-green (61 tests, PostgreSQL triggers + RLS
verified live — see STATE.md and DEPLOYMENT.md). What does NOT exist yet: a
user interface, real user/tenant authentication, real HMRC and Open Banking
integrations (both are mocks), and the P&L/BS/ageings report pack from the
original Wk 24–25 scope.

## Fixed constraints (carried over from PLAN.md — never violate)
1. Founder works 4 hours/day (~88 hrs/month). Stages are sized to this.
2. Lean cash cost first. No paid service until a gate demands it.
3. Gated sequence: no stage starts until the previous gate passes.
4. Definition of done unchanged: code + tests + migrations on a stage branch;
   regression suite green in CI; STATE.md updated; BUILDLOG.md appended.

## Standing decisions for this phase (defaults — change only deliberately)
- **UI approach: server-rendered Django templates + HTMX.** One codebase, no
  separate frontend build/deploy, fastest path for a solo founder, and the
  admin aesthetic is acceptable for accountant-supervised design partners.
  A REST API can be extracted later; nothing in this choice blocks that.
- **Open Banking aggregator: GoCardless Bank Account Data** (free tier: 50
  connections; operates under their AISP permissions, no FCA licence needed).
  TrueLayer is the fallback if coverage of a design partner's bank is missing.
- **Hosting: single small VPS** (e.g. Hetzner/DO, ~£10–20/mo) running
  docker-compose.prod.yml behind Caddy for automatic TLS, plus managed or
  cron-based nightly pg_dump to object storage. No Kubernetes, no PaaS.
- **Error tracking: Sentry free tier** from Stage 7 onwards.

## Do-first (Week 0, alongside Stage 7 — long lead times)
- [ ] Register on the HMRC Developer Hub, create the MTD VAT sandbox
      application, request production credentials (approval can take weeks —
      apply now, build later).
- [ ] Open a GoCardless Bank Account Data sandbox account.
- [ ] Move the working copy OUT of OneDrive and disable the auto-commit
      watcher for this repo (OneDrive sync + git + auto-push has already
      injected spurious commits; it risks corrupting the .git directory).
- [ ] Point a domain at the VPS; stand up staging with SECURE_TLS=True.

---

## Stage 7 — Identity, tenancy & access (~35 founder-hours)
Branch: stage-7-identity
- UserProfile model: auth.User ↔ Tenant link, role enum
  (FirmAdmin / Accountant / ClientUser), is_active, invited_by.
- Invitation flow (email link, expiring token) instead of open signup.
- TenantMiddleware reads the profile for ClientUsers; Accountant/FirmAdmin get
  an explicit tenant-switcher (session-scoped, audited via AuditEvent).
- Login/logout/password reset (Django auth views, styled minimally).
- Run staging with the restricted ledgerhouse_app DB role from day one so
  RLS is load-bearing, not decorative (accounting.W001 must be silent).
- Tests: full role×action matrix; cross-tenant attack tests through the HTTP
  layer (not just the ORM); invitation expiry/reuse.

**GATE 7:** a ClientUser sees exactly one tenant end-to-end over HTTP; an
Accountant can switch tenants and every switch is audit-logged; W001 silent
on staging; suite green.

## Stage 8 — Web UI core + report pack (~110 founder-hours; the big one)
Branch: stage-8-ui
Screens, in build order (each shippable alone):
1. Tenant dashboard (reuse console.py metrics) + accountant firm dashboard.
2. Review queue: journals in RequiresReview → approve/reject with evidence
   side-panel (this is the daily-driver screen for the accountant).
3. Bank import wizard: upload CSV → preview/validation errors → import →
   reconciliation workbench (match suggestions, confirm, skip).
4. Journal browser + manual journal entry form (balanced-by-construction UI).
5. Evidence upload & linking (drag-drop onto a journal).
6. Report pack — the missing Wk 24–25 scope: P&L, Balance Sheet, aged
   debtors/creditors, VAT summary, departmental P&L; every report line
   drills to journals → lines → evidence in ≤3 clicks; CSV export.
7. Period close screen: run run_accountant_audit_check, show blockers,
   close period, lock VAT quarter (wraps existing audit.py functions).
- Playwright smoke tests for the 7 critical paths, run in CI.

**GATE 8:** an accountant completes a full synthetic month (import → review →
reconcile → reports → close) entirely in the browser, and the report pack
matches the fixture expected_results to the penny.

**BUSINESS GATE (unchanged from PLAN.md):** three paid design-partner deposits
banked before Stage 9 spend begins; Stage 8 output is the demo that sells them.

## Stage 9 — Real Open Banking (~45 founder-hours)
Branch: stage-9-open-banking
- Extract a BankFeedProvider interface; MockOpenBankingClient becomes the
  test implementation (existing tests unchanged).
- GoCardless implementation: institution picker, consent redirect flow,
  requisition/token storage (encrypted at rest — django-fernet-fields or
  app-level Fernet with key from env), 90-day consent expiry surfaced in UI
  (the Expired guard from the Stage 6 audit already handles refusal).
- Scheduled sync: management command + cron/systemd timer (no Celery yet).
- Dedup remains FITID/transaction-id + (tenant, fitid) unique constraint.

**GATE 9:** sandbox bank feed syncs idempotently into the ledger; consent
expiry → reauth flow works; a design partner's real bank connects in staging.

## Stage 10 — Real HMRC MTD VAT (~45 founder-hours + external lead time)
Branch: stage-10-mtd
- OAuth2 authorization-code flow against HMRC sandbox; token store per tenant
  (encrypted, refresh handling).
- Fraud Prevention Headers (Gov-Client-*) — mandatory, validated via HMRC's
  Test Fraud Prevention Headers API.
- Endpoints: retrieve obligations (drives "what's due" on the dashboard),
  submit 9-box return (serializer already exists), retrieve
  liabilities/payments for display.
- Submission flow wired to the existing lock: obligations → draft → accountant
  confirms → submit → store receipt → lock_vat_period. Idempotent retry on
  timeout (HMRC returns the receipt for duplicate periodKey).
- Pass HMRC sandbox compliance checks; apply for production credentials.

**GATE 10:** end-to-end sandbox submission accepted with valid fraud headers;
receipt stored; period locked; obligations displayed; production credentials
application submitted.

## Stage 11 — Storage & matching hardening (~30 founder-hours)
Branch: stage-11-hardening
- EvidenceDocument → S3-compatible object storage (Backblaze B2 or Hetzner
  object storage; ~£0). Keep sha256 + size in DB for integrity; lazy
  migration command for existing blobs; signed URLs for download.
- ReconciliationAllocation child table: one bank transaction → many journals
  with amounts; DB constraint that allocations sum to the transaction amount;
  write-off threshold (default £0.05) posting to a small-differences nominal.
  Workbench UI gains split-match support.
- Explicitly deferred still: multi-currency, payroll calculation/RTI, PDF bank
  statement parsing, AI classification beyond existing VatDecisionRule.

**GATE 11:** part-payment and multi-invoice golden datasets reconcile; evidence
survives migration with matching checksums; suite green.

## Stage 12 — Ops & client-zero go-live (~30 founder-hours)
Branch: stage-12-golive
- Nightly pg_dump to object storage + documented, REHEARSED restore drill.
- Sentry wired; log retention; uptime monitor (free tier).
- Security pass: dependency audit, Django deploy checklist, rate-limit login,
  session hardening; verify RLS as the restricted role in production.
- Onboarding runbook: create tenant, chart of accounts template (care-sector
  default), invite users, connect bank, first import.
- Client-zero parallel month (matches STATE.md "Next"): run a real company's
  month alongside their existing bookkeeping; accountant signs off the close.

**GATE 12 (go-live):** client-zero month closes to the accountant's
satisfaction; restore drill documented and repeated; then flip the GitHub repo
back to private and fix the Actions billing block (private-repo CI needs it).

---

## Sequencing & effort summary
| Stage | Effort | Calendar (at ~88 h/mo) | Hard dependency |
|---|---|---|---|
| 7 Identity | ~35 h | 2 weeks | — |
| 8 UI + reports | ~110 h | 5–6 weeks | 7 |
| 9 Open Banking | ~45 h | 2–3 weeks | 7 (UI pieces from 8) |
| 10 MTD VAT | ~45 h | 2–3 weeks | 7; HMRC approval clock started Week 0 |
| 11 Hardening | ~30 h | 1–2 weeks | 8 (workbench UI) |
| 12 Ops & go-live | ~30 h | 2 weeks | all |

Total ≈ 295 founder-hours ≈ 3.5–4.5 months at 4 h/day. Stages 9 and 10 can
interleave while waiting on external approvals. Running cash cost during the
phase: VPS + domain only (~£15–25/mo); everything else on free tiers.

## Top risks
1. **HMRC production approval lead time** — mitigated by Week-0 registration.
2. **Stage 8 scope creep** — the screen list above is the freeze; anything
   else goes to a Phase 5 list.
3. **OneDrive-hosted git working copy** — move it before Stage 7 starts.
4. **Design-partner gate slips** — if deposits aren't banked by end of
   Stage 8, build pauses for sales exactly as PLAN.md prescribes.
