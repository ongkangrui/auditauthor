import pytest
from conftest import observation

from auditauthor.adapters.pdf import extract_pdf, make_chunks
from auditauthor.domain.models import Observation
from auditauthor.services.evidence import deduplicate, validate_observation


def test_pdf_preserves_physical_page(pdf_bytes):
    pages = extract_pdf(pdf_bytes, 10)
    assert pages[0]["number"] == 1
    assert "Agency A" in pages[0]["text"]
    assert not pages[0]["warning"]


def test_invalid_pdf():
    with pytest.raises(ValueError, match="Invalid"):
        extract_pdf(b"not a pdf", 10)


def test_chunks_cover_every_character_and_overlap():
    pages = [{"number": 1, "text": "abcdefghij"}, {"number": 2, "text": "klmnopqrst"}]
    chunks = make_chunks(pages, 8, 2)
    all_text = "".join(p["text"] for c in chunks for p in c["parts"])
    assert all(char in all_text for char in "abcdefghijklmnopqrst")
    assert chunks[0]["parts"][0]["text"][-2:] == chunks[1]["parts"][0]["text"][:2]


def test_evidence_whitespace_only_normalization(pdf_bytes):
    pages = extract_pdf(pdf_bytes, 10)
    report = {"id": "report", "pages": pages}
    chunk = make_chunks(pages, 500, 50)[0]
    item = Observation(**observation())
    item.evidence[0].excerpt = item.evidence[0].excerpt.replace(" ", "\n ")
    assert validate_observation(item, report, chunk).report_id == "report"
    item.evidence[0].excerpt = "Agency A permits unmonitored root access."
    with pytest.raises(ValueError, match="does not match"):
        validate_observation(item, report, chunk)


def test_reject_wrong_page_and_out_of_chunk(pdf_bytes):
    report = {"id": "report", "pages": extract_pdf(pdf_bytes, 10)}
    item = Observation(**observation())
    with pytest.raises(ValueError, match="outside"):
        validate_observation(item, report, {"parts": []})
    item.evidence[0].page = 2
    with pytest.raises(ValueError, match="page 2"):
        validate_observation(item, report, {"parts": []})


def test_dedup_preserves_subfindings_and_reports():
    a = {**observation(), "id": "a", "report_id": "r1"}
    duplicate = {**a, "id": "b"}
    other = {**a, "id": "c", "title": "Other weakness"}
    year = {**a, "id": "d", "report_id": "r2"}
    assert len(deduplicate([a, duplicate, other, year])) == 3
