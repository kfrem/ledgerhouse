# LedgerHouse Additional Companies House Examples - Follow-up

Date: 30 July 2026

## Purpose

Provide three further, distinct XML Gateway test examples for each Companies
House accounts filing type that LedgerHouse currently supports, following the
XML Team's request.

## Submission Matrix

| Filing type | Scenario | Submission number | Immediate polled result |
| --- | --- | --- | --- |
| Micro-entity | Loss-making | `000009` | Pending; no gateway message |
| Micro-entity | Fixed-assets | `000010` | Pending; no gateway message |
| Micro-entity | Creditor-heavy | `000011` | Pending; no gateway message |
| Small unaudited full | Asset-led | `000012` | Pending; no gateway message |
| Small unaudited full | Low-margin | `000013` | Pending; no gateway message |
| Small unaudited full | Loss-making | `000014` | Pending; no gateway message |
| Small unaudited filleted | Services | `000015` | Pending; no gateway message |
| Small unaudited filleted | Fixed-assets | `000016` | Pending; no gateway message |
| Small unaudited filleted | Creditor-led | `000017` | Pending; no gateway message |
| Dormant | Capitalised | `000018` | Pending; no gateway message |
| Dormant | Reserves | `000019` | Pending; no gateway message |
| Dormant | Funded | `000020` | Pending; no gateway message |

## Controls and Verification

- Pre-send local scenario validation passed for all 18 Companies House
  scenarios, including all 12 new scenarios.
- The submission sequence was confirmed at `000008` before sending, and the
  new records were allocated sequentially through `000020`.
- The controlled batch command records a unique run label and will not resend
  an existing item if it is run again.
- Each test was sent with the Gateway test flag and then polled immediately.
- The credentials were removed from the container after the operation and are
  not stored in the repository.
- Focused Companies House tests and the full test suite are rerun after this
  submission pass; their results are recorded in the terminal evidence.

## Status Boundary

`Pending` is not acceptance. The next external action is for the XML Team to
review submissions `000009` through `000020`. Production filing remains
disabled until formal Companies House approval is given.
