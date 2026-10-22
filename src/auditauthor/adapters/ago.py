from urllib.parse import urljoin, urlparse

import httpx


def check_url(url: str):
    parsed = urlparse(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in {"www.ago.gov.sg", "ago.gov.sg"}
        or parsed.port not in (None, 443)
        or parsed.username
        or parsed.password
    ):
        raise ValueError("Use an HTTPS PDF link on www.ago.gov.sg or ago.gov.sg.")


def download_report(url: str, max_bytes: int) -> tuple[bytes, str]:
    current = url
    with httpx.Client(timeout=60, follow_redirects=False) as client:
        for _ in range(5):
            check_url(current)
            with client.stream("GET", current) as response:
                if response.is_redirect:
                    current = urljoin(current, response.headers["location"])
                    continue
                response.raise_for_status()
                data = bytearray()
                for block in response.iter_bytes():
                    data.extend(block)
                    if len(data) > max_bytes:
                        raise ValueError("Downloaded PDF exceeds size limit.")
                return bytes(data), current
    raise ValueError("Too many redirects from AGO.")
