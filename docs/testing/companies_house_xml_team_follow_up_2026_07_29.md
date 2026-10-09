# LedgerHouse Companies House XML Team Follow-up - 29 July 2026

## XML Team Scope Confirmation

The XML Team confirmed that amended accounts are variants of the supported
accounts filing types rather than a separate LedgerHouse product filing type.
The declared initial scope is therefore:

1. Micro-entity accounts
2. Small unaudited full accounts
3. Small unaudited filleted accounts
4. Dormant company accounts

Amended micro-entity accounts remain covered by prior test submission `000004`
and by the local amended-variant scenario.

## Authorised XML Gateway Test Batch

The controlled batch was sent using the next unique and incremental numbers
for the LedgerHouse product sequence:

| Submission number | Filing type | Immediate polled status | Gateway messages |
| --- | --- | --- | --- |
| `000005` | Small unaudited filleted accounts | Pending | None |
| `000006` | Micro-entity accounts | Pending | None |
| `000007` | Small unaudited full accounts | Pending | None |
| `000008` | Dormant company accounts | Pending | None |

The immediate poll recorded no rejection message. `Pending` means the Gateway
has not supplied a final accepted or rejected result; it must not be described
as acceptance.

## Controls Applied

- Existing submitted sequence was verified as `000001` to `000004` before the
  batch began.
- The controlled command allocates numbers through the existing atomic product
  sequence and refuses duplicate reruns for the same XML Team review batch.
- The send gate was enabled only for the one container command used for this
  batch.
- Filing credentials were removed from the running container immediately after
  the send and poll operation.
- The persistent local credentials file was not added to the repository.
- The XML Team run report and evidence ZIP are sanitised and contain no
  presenter ID, authentication value or company authentication code.

## Verification After Transmission

| Check | Result |
| --- | --- |
| Focused Companies House tests | 36 passed |
| Full Django test suite | 188 passed in 59.756 seconds |
| Migration check | Passed; no changes detected |
| Django system check | Passed; no issues |
| Controlled command idempotency | Passed; second run identified `000005` to `000008` and did not resend |
| Credentials in running container after send | Not present |

## Evidence and Next Action

- Run record: `docs/testing/companies_house_xml_team_round_2026_07_29.md`
- Sanitised reviewer archive: `output/companies_house/review/ledgerhouse_ch_xml_team_round_2026_07_29.zip`
- Reply draft: `docs/correspondence/companies_house_xml_team_round_reply_2026_07_29.md`

Send the prepared reply to Ioan, identifying submissions `000005`, `000006`,
`000007` and `000008`, then await the XML Team's review. No production filing
must be enabled until formal approval is received.
