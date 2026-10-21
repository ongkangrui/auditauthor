"""Explicit paid live evaluation, followed by independent semantic scoring.

Run: python tests/evaluation/evaluate.py --live
Then review evaluation-results/review.json and run --score PATH.
"""

import argparse
import json
import os
from pathlib import Path

from dotenv import load_dotenv

from auditauthor.adapters.llm import LiteLLMClient
from auditauthor.config import Settings
from auditauthor.domain.models import PROMPT_VERSION, Extraction
from auditauthor.prompts import EXTRACT
from auditauthor.services.evidence import validate_observation

ROOT = Path(__file__).resolve().parents[2]


def live():
    load_dotenv()
    settings = Settings()
    if not settings.model or not os.getenv("OPENAI_API_KEY"):
        raise SystemExit("Set AUDIT_MODEL and OPENAI_API_KEY before live evaluation.")
    benchmark = json.loads((ROOT / "docs/EVALUATION_SET.json").read_text(encoding="utf-8"))
    client = LiteLLMClient(settings)
    results = {
        "model": settings.model,
        "prompt_version": PROMPT_VERSION,
        "human_review_complete": False,
        "cases": [],
    }
    output = ROOT / "evaluation-results"
    output.mkdir(exist_ok=True)
    for case in benchmark["cases"]:
        chunk = {
            "parts": [{"page": p["number"], "text": p["text"]} for p in case["pages"]],
            "agency_context": case["agency_context"],
            "system_context": case["system_context"],
        }
        result, resolved = client.generate(EXTRACT, json.dumps(chunk), Extraction, settings.model)
        predictions = []
        for index, observation in enumerate(result.observations):
            try:
                validate_observation(
                    observation, {"id": case["report_sha256"], "pages": case["pages"]}, chunk
                )
                citation_valid = True
            except ValueError:
                citation_valid = False
            predictions.append(
                {
                    "id": f"{case['id']}-prediction-{index}",
                    "observation": observation.model_dump(mode="json"),
                    "citation_valid": citation_valid,
                    "matched_expected_id": None,
                    "semantically_supported": None,
                }
            )
        results["cases"].append(
            {
                "id": case["id"],
                "input": chunk,
                "expected": case["expected"],
                "resolved_model": resolved,
                "predictions": predictions,
            }
        )
        (output / "review.json").write_text(
            json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    print(f"Review predictions and fill match/support fields in {output / 'review.json'}.")


def score(path):
    review = json.loads(path.read_text(encoding="utf-8"))
    benchmark = json.loads((ROOT / "docs/EVALUATION_SET.json").read_text(encoding="utf-8"))
    expected_cases = {c["id"]: c["expected"] for c in benchmark["cases"]}
    actual_cases = {c["id"]: c["expected"] for c in review["cases"]}
    if actual_cases != expected_cases or len(review["cases"]) != len(expected_cases):
        raise SystemExit("Scoring requires every benchmark case with unchanged expected labels.")
    if not review["human_review_complete"]:
        raise SystemExit("Independent review must be completed before reporting semantic metrics.")
    expected_count, accepted_count, true_positives, raw_count, valid_count = 0, 0, 0, 0, 0
    for case in review["cases"]:
        expected = {e["id"] for e in case["expected"]}
        expected_count += len(expected)
        matched = set()
        for prediction in case["predictions"]:
            raw_count += 1
            valid_count += bool(prediction["citation_valid"])
            if prediction["semantically_supported"] not in (True, False):
                raise SystemExit("Every prediction needs a semantic-support judgment.")
            target = prediction["matched_expected_id"]
            if target is not None and target not in expected:
                raise SystemExit("Match must reference an expected ID in the same case.")
            if prediction["citation_valid"]:
                accepted_count += 1
                if target and target not in matched and prediction["semantically_supported"]:
                    true_positives += 1
                    matched.add(target)
    metrics = {
        "precision": true_positives / accepted_count if accepted_count else 0,
        "recall": true_positives / expected_count if expected_count else 0,
        "raw_citation_validity": valid_count / raw_count if raw_count else 0,
        "accepted_citation_validity": 1.0 if accepted_count else None,
    }
    print(json.dumps(metrics, indent=2))
    if metrics["precision"] < 0.9 or metrics["recall"] < 0.8:
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--live", action="store_true")
    mode.add_argument("--score", type=Path)
    args = parser.parse_args()
    live() if args.live else score(args.score)
