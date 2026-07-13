# Live HMRC Release Gate

Date: 2026-07-13

This gate must be completed before any real HMRC production filing is enabled.

## Gate 1 - HMRC Approval

- HMRC production credentials approved.
- Production client ID stored outside Git.
- Production client secret stored outside Git.
- Correct production API subscriptions visible in HMRC Developer Hub.

## Gate 2 - Production Environment

- Public HTTPS deployment active.
- Production redirect URI registered in HMRC Developer Hub.
- `HMRC_VENDOR_PUBLIC_IP` set to the real public egress/ingress IP.
- `HMRC_VENDOR_VERSION` set to the release version.
- `check_production_readiness --strict` passes.

## Gate 3 - Controlled OAuth Test

- Use one authorised controlled business/client.
- Complete HMRC OAuth authorisation.
- Confirm token is encrypted at rest.
- Retrieve obligations only.
- Do not submit a return during this step.

## Gate 4 - Controlled Filing Test

- Confirm the VAT period is correct.
- Confirm the nine-box VAT payload.
- Confirm practice checklist completed.
- Confirm client approval completed.
- Confirm user explicitly approves the filing test.
- Submit once.
- Save HMRC receipt ID and evidence.

## Gate 5 - Release Decision

- If the controlled filing succeeds, document the result.
- If HMRC rejects or returns an error, keep live filing disabled and fix/test locally first.
- Do not enable broad customer filing until the controlled filing evidence is accepted internally.
