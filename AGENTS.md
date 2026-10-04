# Trad3r engineering agreement

The owner has authorised autonomous development in small feature-branch PRs,
including merging after review and verification. Never commit directly to main.

- Keep each PR focused. Read the current repository and preserve concurrent changes.
- Perform a separate review pass on every proposed diff. Fix findings before merge.
  Record reviewed head SHA, test evidence and remaining scope limits in the PR body.
  Do not describe self-review as an independent human or second-agent approval.
- Require passing hosted CI on the reviewed commit before merging. Merge with an
  expected head SHA so a changed branch cannot be merged under an older review.
- Maintain README, engineering contracts and roadmap as behaviour changes. Use
  deterministic synthetic tests; licensed samples and secrets stay out of git.
- Prioritise cash accounting, settlement, risk persistence and conservative fill
  semantics before strategy optimisation or classifier integration.
- The agreed limits are GBP 1000 initial funding, GBP 300 absolute cumulative loss,
  GBP 10 session loss, GBP 25 weekly loss and GBP 3 planned all-in trade risk.
  AI must not weaken limits or reset a halt. Do not automatically renew loss budgets.
- Development authority does not authorise opening/funding accounts, paid services,
  placing trades or enabling live execution. Keep those capabilities disabled.
- Finish each work session with completed PRs, validation evidence and an explicit
  next backlog. Do not imply that work continues unattended after the session ends.
