<!--
Thanks for the PR! Please complete the sections below. Incomplete PRs get
deprioritized.

For your first contribution, the CLA Assistant bot will comment with a one-line
acknowledgment to sign. CI must be green before review.

Conventions: see CONTRIBUTING.md.
-->

## Summary

<!--
One paragraph: what changed and why. The "why" is the load-bearing part —
the diff already shows the "what".
-->

## Linked issue / spec

<!-- e.g. Closes #123, or "follow-up to docs/11 F4" -->

## Type

<!-- Pick one. Delete the others. -->
- bug fix
- feature
- refactor (no behavior change)
- docs
- chore / build / CI

## Test plan

<!--
What did you actually run? Paste the pytest output, or describe the manual
verification. CI alone is not a test plan — say what behavior you exercised.
-->

- [ ] `pytest` passes locally
- [ ] `ruff check .` and `ruff format --check .` clean
- [ ] `mypy app cli` clean (if you touched typed code)
- [ ] New tests added for new code paths
- [ ] Manual verification (if applicable, describe below)

## Doc changes

<!--
If your PR changes a documented decision in docs/01-docs/11, update the doc
in the same PR. Schema changes need docs/04. Prompt changes need a version bump
in docs/05. State-machine edges need docs/04 + docs/06.
-->

- [ ] No doc impact
- [ ] Updated relevant doc(s): <!-- list -->

## Compatibility / migration

<!--
Did you add an Alembic migration? Did you change a public API or CLI surface?
Will operators need to do anything on upgrade?
-->

- [ ] No migration / no breaking change
- [ ] New Alembic migration (file: <!-- path -->)
- [ ] Breaking change to API / CLI / SDK (describe and bump version)

## Checklist

- [ ] I have signed the [CLA](../CLA.md) (the bot will prompt on this PR if not).
- [ ] I have read [CONTRIBUTING.md](../CONTRIBUTING.md) and followed the conventions.
- [ ] I did not edit a previously committed Alembic migration.
- [ ] No secrets, API keys, customer text, or PII in this diff.
- [ ] No commented-out code or stray debug prints.
