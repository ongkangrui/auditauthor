"""Rebuild source excerpts for the explicitly reviewed benchmark definitions.

Labels are agent-reviewed candidates, not a claim of independent auditor approval.
"""

import hashlib
import json
from pathlib import Path

import pymupdf

from auditauthor.services.evidence import normalize

ROOT = Path(__file__).resolve().parents[2]

# Each input is a literal passage, with the relevant agency/system provided as context.
DEFINITIONS = [
    (
        "2022_23",
        32,
        "PSD",
        "HRP",
        "30.",
        "31.",
        ["Misconfigured OS security software permits unrestricted root commands"],
    ),
    (
        "2022_23",
        32,
        "PSD",
        "HRP",
        "32.",
        None,
        ["Most privileged database account used for routine monitoring"],
    ),
    (
        "2022_23",
        33,
        "PSD",
        "HRP",
        "33.",
        "34.",
        ["Privileged database account lacks failed-login lockout"],
    ),
    (
        "2022_23",
        33,
        "PSD",
        "HRP",
        "36.",
        "5 Service",
        [
            "No monthly reviews of privileged application accounts",
            "Incomplete monthly server and database account reviews",
        ],
    ),
    (
        "2022_23",
        34,
        "PSD",
        "HRP",
        "c.",
        "37.",
        ["Quarterly account and access-right reviews not conducted"],
    ),
    (
        "2022_23",
        34,
        "PSD",
        "HRP",
        "40.",
        None,
        [
            "Missing OS administrator activity review due to SIEM collection failure",
            "Database administrator activities not reviewed for six months",
        ],
    ),
    (
        "2022_23",
        35,
        "PSD",
        "HRP",
        "b.",
        "41.",
        [
            "Activity review lacks details and omits important activities",
            "No assessment or documentation of anomaly follow-up",
            "Database activity reviewer did not evidence authorization checks",
        ],
    ),
    (
        "2022_23",
        97,
        "STB",
        "STAN",
        "133.",
        "13 The",
        ["Shared most-privileged database account prevents individual traceability"],
    ),
    (
        "2022_23",
        98,
        "STB",
        "STAN",
        "134.",
        "B.",
        ["Database privileges exceed job needs and are used by non-administrators"],
    ),
    (
        "2022_23",
        98,
        "STB",
        "STAN",
        "135.",
        "136.",
        ["Misconfigured OS software permits all root commands"],
    ),
    (
        "2023_24",
        84,
        "MSF",
        "GPLS",
        "78.",
        "79.",
        [
            "Privileged OS access lacks assessment",
            "No sudo configuration review leaves redundant root-capable account",
        ],
    ),
    (
        "2023_24",
        84,
        "MSF",
        "GPLS",
        "80.",
        "14 The",
        [
            "Shared privileged application account",
            "Incomplete and insufficient privileged-activity review logs",
        ],
    ),
    (
        "2023_24",
        85,
        "MSF",
        "BBO",
        "81.",
        "82.",
        ["Privileged access exceeds job requirements", "No review of privileged user activities"],
    ),
    (
        "2023_24",
        104,
        "ECDA",
        "CMS",
        "142.",
        "143.",
        [
            "Unassessed unrestricted root privileges",
            "No sudo configuration reviews leave obsolete privileged accounts",
        ],
    ),
    (
        "2023_24",
        105,
        "ECDA",
        "CMS",
        "144.",
        "145.",
        [
            "No privileged activity reviews since implementation",
            "Missing authorization evidence for privileged activity",
        ],
    ),
    (
        "2023_24",
        105,
        "ECDA",
        "CMS",
        "145.",
        "146.",
        [
            "Incomplete internal user access reviews",
            "Inadequate follow-up of external user access reviews",
            "Delayed removal of obsolete CMS accounts",
        ],
    ),
    (
        "2024_25",
        34,
        "MOM",
        "WINS-EP",
        "35.",
        "36.",
        ["Inappropriate command enables root password changes"],
    ),
    (
        "2024_25",
        34,
        "MOM",
        "WINS-EP",
        "38.",
        "39.",
        ["Remote root login permitted contrary to console-only policy"],
    ),
    (
        "2024_25",
        35,
        "MOM",
        "WINS-EP",
        "40.",
        "41.",
        ["Root account used for routine operations rather than emergencies"],
    ),
    ("2024_25", 35, "MOM", "WINS-EP", "41.", "42.", ["Root password not changed after each use"]),
    (
        "2024_25",
        35,
        "MOM",
        "WINS-EP",
        "43.",
        "44.",
        ["Privileged activity review covers only one activity type"],
    ),
    ("2022_23", 74, "IRAS", None, "d.", "51.", []),
    ("2024_25", 73, "A*STAR", "iGrants", "b.", "c.", []),
    ("2023_24", 85, "MSF", "BBO", "83.", None, []),
    ("2023_24", 104, "ECDA", "CMS", "143.", None, []),
]


def main():
    cases = []
    for index, (year, page, agency, system, start, end, labels) in enumerate(DEFINITIONS, 1):
        path = ROOT / "input" / f"ar_fy{year}.pdf"
        with pymupdf.open(path) as doc:
            source = normalize(doc[page - 1].get_text(sort=True))
        begin = source.index(start)
        finish = source.index(end, begin + len(start)) if end else len(source)
        excerpt = source[begin:finish].strip()
        cases.append(
            {
                "id": f"case-{index:02d}",
                "report": path.name,
                "report_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "agency_context": agency,
                "system_context": system,
                "pages": [{"number": page, "text": excerpt}],
                "expected": [
                    {"id": f"case-{index:02d}-finding-{i}", "weakness": label}
                    for i, label in enumerate(labels, 1)
                ],
            }
        )
    data = {
        "version": "1.0",
        "review_status": "agent-reviewed; independent human review pending",
        "targets": {"precision": 0.9, "recall": 0.8, "citation_validity": 1.0},
        "notes": "Passage-level labels. Full-report and consolidation quality require separate review. "
        "Context is supplied for passage tests; full-report tests must infer attribution.",
        "cases": cases,
        "integration_scenarios": [
            {
                "name": "cross-page finding",
                "report": "ar_fy2022_23.pdf",
                "pages": [33, 34],
                "assertion": "Keep monthly and quarterly account review sub-findings distinct; preserve PSD/HRP context.",
            },
            {
                "name": "agency boundary",
                "report": "ar_fy2024_25.pdf",
                "pages": [32, 33, 34],
                "assertion": "Attribute preceding IPTO observations to MinLaw, WINS-EP observations to MOM.",
            },
            {
                "name": "overview and detail duplication",
                "report": "ar_fy2024_25.pdf",
                "pages": [19, 33, 34, 35],
                "assertion": "Do not count the MOM overview as an additional independent finding.",
            },
            {
                "name": "report with few explicit IT terms",
                "report": "ar_fy2021_22.pdf",
                "pages": "all",
                "assertion": "Review all text; do not assume zero technology observations from keyword absence.",
            },
        ],
    }
    (ROOT / "docs" / "EVALUATION_SET.json").write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(
        f"Wrote {len(cases)} cases, {sum(len(c['expected']) for c in cases)} expected observations."
    )


if __name__ == "__main__":
    main()
