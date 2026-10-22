# Architecture and required functionality

## Boundaries

`api/` handles upload limits, validation responses, exports and job submission.
`ui/` uses only HTTP; it cannot read the backend volume or call the model.
`domain/` defines model-output contracts, themes and narrow service ports.
`services/` owns ingestion, evidence acceptance, consolidation and job execution.
`adapters/` implements PDF parsing, LiteLLM, SQLite and official AGO downloads.
`prompts/` contains versioned extraction/consolidation instructions.

These boundaries implement KISS and SOLID without unnecessary base classes.
The model client and analysis store are injectable; tests use a fake model and
temporary SQLite. The frontend only filters and renders existing results.

## Persistence and lifecycle

Reports are identified by SHA-256 of bytes. SQLite stores report metadata, extracted
pages and job aggregates; `/data/reports/<hash>.pdf` stores originals. No user-supplied
filename is used as a storage path. Repeated uploads reuse the report record.

Jobs contain immutable selected report IDs, configured model, prompt/schema versions,
chunk settings, returned model identifiers, per-chunk results/errors, consolidation
cache, accepted findings, insights, coverage and retry history. A persisted queue
has at most eight queued/running jobs by default. One backend worker claims the
oldest job atomically and processes chunks serially.

States: queued -> running -> complete/partial/failed/interrupted. On startup,
previously running jobs become interrupted; queued work resumes. Explicit retries
reuse completed extraction and successful consolidation where its inputs have not
changed. Incompatible prompt/schema versions require a new analysis. No SQL
migration is needed for the initial greenfield schema; future persisted-contract
changes need an explicit compatibility decision.

## Public API

| Method | Path | Behavior |
|---|---|---|
| GET | /health | Service and model/credential configuration status, never secrets |
| POST / GET | /reports | Multipart upload / metadata listing |
| GET | /reports/{id}/file | Original PDF |
| POST / GET | /analyses | Submit report IDs / list saved analyses |
| GET | /analyses/{id} | Status, model provenance, coverage, errors |
| GET | /analyses/{id}/findings | Validated observations |
| GET | /analyses/{id}/insights | Supported consolidated insights |
| POST | /analyses/{id}/retry | Retry partial, failed or interrupted job |
| GET | /analyses/{id}/export?format=csv\|json | Findings CSV or full JSON review result |

Submission returns HTTP 202. Unknown IDs return 404; invalid PDF/schema returns
422; oversized upload 413; full queue 429; missing model configuration 503; invalid
retry state 409. OpenAPI at `/docs` is the executable request contract.

Observation fields: title, nullable agency/system, taxonomy theme, weakness, nullable
reported risk/remediation, detail/overview designation, evidence array, ID, report ID.
Evidence includes physical PDF page and literal excerpt. Insights include supporting
IDs, theme, specific weakness, cautious audit implication and calculated report,
agency and repeated-entity counts. The model cannot directly set recurrence counts.

## Review and failure behavior

All text is considered, including technology observations outside IT headings.
Whitespace-normalized evidence must exist in both source page and supplied chunk.
Accepted partial findings remain reviewable when other work fails. Invalid outputs,
provider failures and image-dominant pages are visible; partial coverage is never
represented as complete. A successful run with no findings is a valid result.

Summaries are not counted as independent occurrences when deduplicated against
detailed findings. Same-report duplicates cannot cross agency/system boundaries.
Unknown entities are not semantically merged. Semantic equivalence and entailment
remain model judgments requiring auditor review; exact quotations are necessary
but insufficient proof of a correct finding.

## Acceptance mapping

- Assessment AI approach: explicit single-model configuration, two prompts, strict
  schema, quote verification, consolidation references and model provenance.
- Audit relevance: fixed IT-control themes, explicit weaknesses, remediation separated,
  cross-report recurrence, source inspection and exports.
- Design justification: two containers, injected boundaries, no retrieval/agent stack.
- Evaluation: offline contract/failure tests, four-report parsing, independently scored
  live benchmark and manual cross-report scenario review.
- Submission: README setup, assumptions, challenges, limitations and future work.
