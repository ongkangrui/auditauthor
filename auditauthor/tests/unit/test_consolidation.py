import pytest
from conftest import FakeModel, observation

from auditauthor.domain.models import Consolidation
from auditauthor.services.consolidation import consolidate_theme


def finding(id, report, agency="Agency A"):
    return {**observation(agency=agency), "id": id, "report_id": report}


def test_recurrence_distinct_reports_and_entities():
    _, insights, _ = consolidate_theme(
        FakeModel(), [finding("a", "r1"), finding("b", "r1")], "fake"
    )
    assert not insights[0]["recurring"]
    _, insights, _ = consolidate_theme(
        FakeModel(), [finding("a", "r1"), finding("b", "r2")], "fake"
    )
    assert insights[0]["recurring"]
    assert insights[0]["report_count"] == 2
    assert insights[0]["repeated_entities"] == [{"agency": "Agency A", "system": "Alpha"}]


def test_unknown_reference_rejected():
    class BadModel:
        def generate(self, *args):
            return Consolidation(
                insights=[
                    {
                        "theme": "logging/monitoring",
                        "weakness": "x",
                        "audit_implication": "x",
                        "observation_ids": ["invented"],
                    }
                ],
                duplicate_groups=[],
            ), "fake"

    with pytest.raises(ValueError, match="unknown"):
        consolidate_theme(BadModel(), [finding("a", "r1")], "fake")


def test_cross_report_dedup_rejected():
    class BadModel:
        def generate(self, *args):
            return Consolidation(insights=[], duplicate_groups=[["a", "b"]]), "fake"

    with pytest.raises(ValueError, match="boundaries"):
        consolidate_theme(BadModel(), [finding("a", "r1"), finding("b", "r2")], "fake")
