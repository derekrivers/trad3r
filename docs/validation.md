# Offline foundation validation

Checked 4 October 2026 with Python 3.12.14.

- 18 unittest cases passed, including nine agreed cumulative-P&L examples,
  inclusive daily/weekly thresholds, cash-flow adjustments, retained halt reasons,
  invalid money inputs, trade-risk costs, checksum tampering, duplicate bars,
  invalid prices, UTC requirements and output overwrite prevention.
- Replayed the private sample twice: 23,400 raw-price observations, 20 sessions
  per symbol, 390 minute bars per session. Output files matched byte for byte.
- Journal SHA-256:
  `cf33c5bb2e5f2cb104f4c3d488081a081abeb42834dcbe51df5b93c8a6700c84`.
- Input SHA-256:
  `eebd9e7454227356d9b7d1bcbe9e1518bcd18721fdf441a9179e19a3b534074b`.

No trading strategy, simulated fills, cash ledger, profitability test, broker
integration or live execution was tested. The fixture is not redistributed.
Hosted CI is configured for Python 3.11, 3.12 and 3.13; its current status belongs
to the PR checks rather than this local verification record.
