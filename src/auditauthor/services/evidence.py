import hashlib
import re

from auditauthor.domain.models import Finding, Observation


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def validate_observation(observation: Observation, report: dict, chunk: dict) -> Finding:
    pages = {p["number"]: normalize(p["text"]) for p in report["pages"]}
    parts = [(p["page"], normalize(p["text"])) for p in chunk["parts"]]
    for evidence in observation.evidence:
        quote = normalize(evidence.excerpt)
        if quote not in pages.get(evidence.page, ""):
            raise ValueError(f"Evidence does not match physical PDF page {evidence.page}.")
        if not any(page == evidence.page and quote in text for page, text in parts):
            raise ValueError("Evidence refers to text outside this chunk.")
    fingerprint = (
        report["id"]
        + "|"
        + "|".join(f"{e.page}:{normalize(e.excerpt)}" for e in observation.evidence)
        + "|"
        + observation.title.casefold()
    )
    return Finding(
        **observation.model_dump(),
        report_id=report["id"],
        id=hashlib.sha256(fingerprint.encode()).hexdigest()[:24],
    )


def deduplicate(findings: list[dict]) -> list[dict]:
    accepted = []
    for candidate in sorted(findings, key=lambda f: f["source_kind"] != "detail"):
        duplicate = False
        for existing in accepted:
            same_context = all(
                candidate[k] == existing[k] for k in ("report_id", "agency", "system", "theme")
            )
            # Different titles can be distinct sub-findings sharing a paragraph. Do not merge them.
            same_title = (
                normalize(candidate["title"]).casefold() == normalize(existing["title"]).casefold()
            )
            evidence_overlap = any(
                a["page"] == b["page"]
                and (
                    normalize(a["excerpt"]) in normalize(b["excerpt"])
                    or normalize(b["excerpt"]) in normalize(a["excerpt"])
                )
                for a in candidate["evidence"]
                for b in existing["evidence"]
            )
            if candidate["id"] == existing["id"] or (
                same_context and same_title and evidence_overlap
            ):
                duplicate = True
                break
        if not duplicate:
            accepted.append(candidate)
    return accepted
