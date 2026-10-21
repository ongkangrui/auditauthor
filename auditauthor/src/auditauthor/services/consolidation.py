import hashlib
import json

from auditauthor.domain.models import Consolidation
from auditauthor.prompts import CONSOLIDATE


def consolidate_theme(
    client, findings: list[dict], model: str
) -> tuple[list[dict], list[dict], str]:
    payload = json.dumps(findings, ensure_ascii=False)
    if len(payload) > 160000:
        raise ValueError(
            "Theme exceeds consolidation context limit; analyse fewer reports together."
        )
    result, resolved = client.generate(CONSOLIDATE, payload, Consolidation, model)
    result = Consolidation.model_validate(result)
    by_id = {f["id"]: f for f in findings}
    aliases = {}
    for group in result.duplicate_groups:
        if len(group) < 2 or len(set(group)) != len(group) or any(i not in by_id for i in group):
            raise ValueError("Invalid duplicate group from consolidation.")
        if any(i in aliases or i in aliases.values() for i in group):
            raise ValueError("Overlapping duplicate groups.")
        members = [by_id[i] for i in group]
        if any(
            any(f[k] != members[0][k] for k in ("report_id", "agency", "system", "theme"))
            for f in members
        ):
            raise ValueError("Duplicate group crosses report or agency/system boundaries.")
        # Do not trust deduplication when both agency and system are unknown.
        if members[0]["agency"] is None and members[0]["system"] is None:
            continue
        canonical = next((f for f in members if f["source_kind"] == "detail"), members[0])
        for member in members:
            if member["id"] != canonical["id"]:
                aliases[member["id"]] = canonical["id"]
    accepted = [f for f in findings if f["id"] not in aliases]
    covered = set()
    insights = []
    for draft in result.insights:
        if any(i not in by_id for i in draft.observation_ids):
            raise ValueError("Insight cites an unknown observation.")
        ids = sorted({aliases.get(i, i) for i in draft.observation_ids})
        members = [by_id[i] for i in ids]
        if any(f["theme"] != draft.theme.value for f in members):
            raise ValueError("Insight theme disagrees with supporting observations.")
        covered.update(ids)
        reports = sorted({f["report_id"] for f in members})
        agencies = sorted({f["agency"] for f in members if f["agency"]})
        entities = {(f["agency"], f["system"]) for f in members if f["agency"] or f["system"]}
        repeated = [
            {"agency": a, "system": s}
            for a, s in sorted(entities, key=str)
            if len({f["report_id"] for f in members if (f["agency"], f["system"]) == (a, s)}) >= 2
        ]
        insights.append(
            {
                **draft.model_dump(mode="json"),
                "observation_ids": ids,
                "id": hashlib.sha256((draft.weakness + "|".join(ids)).encode()).hexdigest()[:24],
                "report_ids": reports,
                "report_count": len(reports),
                "agencies": agencies,
                "agency_count": len(agencies),
                "recurring": len(reports) >= 2,
                "cross_agency": len(agencies) >= 2,
                "repeated_entities": repeated,
            }
        )
    if covered != {f["id"] for f in accepted}:
        raise ValueError("Consolidation omitted observations.")
    return accepted, insights, resolved
