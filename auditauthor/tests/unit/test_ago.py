import pytest

from auditauthor.adapters.ago import check_url


@pytest.mark.parametrize(
    "url",
    [
        "http://www.ago.gov.sg/a.pdf",
        "https://evil.example/a.pdf",
        "https://www.ago.gov.sg.evil.example/a.pdf",
        "https://user@www.ago.gov.sg/a.pdf",
    ],
)
def test_reject_unofficial_url(url):
    with pytest.raises(ValueError):
        check_url(url)


def test_official_url():
    check_url("https://www.ago.gov.sg/files/a.pdf")


def test_redirect_to_other_host_rejected(monkeypatch):
    import httpx

    from auditauthor.adapters.ago import download_report

    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(302, headers={"location": "https://evil.example/a.pdf"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr("auditauthor.adapters.ago.httpx.Client", lambda **kwargs: client)
    with pytest.raises(ValueError, match="HTTPS PDF link"):
        download_report("https://www.ago.gov.sg/a.pdf", 10000)
    assert len(requests) == 1
