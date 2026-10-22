# Implementation and validation status

## Implemented

- [x] Configuration, typed extraction/insight contracts, SQLite and original PDF persistence.
- [x] Two-container Compose deployment and dependency lock files.
- [x] Upload/import/download, hashes, physical pages and extraction warnings.
- [x] LiteLLM structured extraction, bounded retries and evidence validation.
- [x] Persistent bounded queue, restart recovery and selective retry.
- [x] Deduplication, grounded theme consolidation and calculated recurrence.
- [x] Streamlit source review, filters, coverage display and CSV/JSON exports.
- [x] Architecture, coding-agent rules, decisions, inventory and README.
- [x] Candidate benchmark: 25 cases, 32 expected observations, four negative passages.
- [x] GitHub Actions: tests, lint, Python/dependency/secret scans, weekly security schedule and private-repository billing gate.

## Validation

- [x] Deterministic API/domain/retry tests and all four supplied PDFs parse successfully.
- [x] Benchmark excerpt hashes/text verified against supplied originals.
- [x] Final lint: `ruff check .` passed.
- [x] Deterministic suite: 30 tests passed, including background worker and Streamlit review tests.
- [x] Both Docker images built and services started; backend health check passed.
- [x] HTTP deployment smoke passed: frontend/backend health, four persisted reports,
  original-PDF SHA-256 checks and OpenAPI routes. Reports survived container recreation.
- [ ] Independent human approval of benchmark labels and semantic-support judgments.
- [ ] Live single-model passage evaluation: requires AUDIT_MODEL and OPENAI_API_KEY.
- [ ] Full-report model evaluation and manual consolidation/agency-boundary review.

## CI validation (22 October 2026)

- [x] Full local pytest suite: 30 passed; Ruff passed; Bandit found no issues.
- [x] Exact CI test selection: 25 unit/integration tests passed; locked sync passed,
  runtime requirements regenerated, and Bandit confirmed no skipped files.
- [x] GitHub Actions workflow validated with actionlint 1.7.7.
- [x] Gitleaks 8.24.3 CLI archive checksum verified; existing Git history scan passed.
- [x] Gitleaks scan of current tracked and untracked non-ignored project files passed.
- [ ] Review pip-audit findings: the workflow reports findings in its run summary
  and does not fail for advisories. The locked Pillow 12.3.0 findings remain for
  follow-up because Streamlit 1.66.0 requires Pillow<13 while Pillow 13.0.0 fixes them.
- [ ] First hosted Linux run after committing/pushing required project files.

Precision/recall thresholds are acceptance targets, not measured results. Runtime
credentials and model were not configured during initial implementation.

Verified on 22 October 2026 (Asia/Singapore). Run the deployment smoke again with
`uv run python tests/integration/smoke_deployment.py` after importing samples.
The test suite emits one upstream Starlette/httpx deprecation warning; no test failures.
Container smoke did not run paid model analysis. End-to-end job completion, retries,
exports and review rendering were exercised with a deterministic injected model.
