from app.rag.ingest import split_into_sections


def test_split_into_sections_basic():
    text = "# Title\nintro text\n## Section A\nbody a\n## Section B\nbody b\n"
    sections = split_into_sections(text)
    titles = [t for t, _ in sections]
    assert "Section A" in titles
    assert "Section B" in titles
    body_a = dict(sections)["Section A"]
    assert "body a" in body_a


def test_split_into_sections_no_headings():
    text = "just a flat document with no headings"
    sections = split_into_sections(text)
    assert len(sections) == 1
    assert sections[0][0] == "Overview"


def test_citation_regex_matches_expected_formats():
    from app.eval.metrics import CITATION_RE

    sample = (
        "Root cause supported by log:checkout-service@2026-09-10T14:05:00 and "
        "metric:checkout-service:db_pool_in_use@2026-09-10T14:06:00 and "
        "runbook:checkout-service \u203a Known failure mode: DB connection pool exhaustion"
    )
    matches = [m.group(0) for m in CITATION_RE.finditer(sample)]
    assert any(m.startswith("log:") for m in matches)
    assert any(m.startswith("metric:") for m in matches)
    assert any(m.startswith("runbook:") for m in matches)
