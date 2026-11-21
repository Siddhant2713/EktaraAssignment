"""SSRF: the scraper fetches whatever URL a user types, so it must never be talked into reaching private networks.

Uses the REAL guard (no allow_local fixture). Any PipelineError counts as "blocked".
"""

import pytest

from app.schemas.events import ErrorCode
from app.services.errors import PipelineError
from app.services.scraper import _ensure_public

PRIVATE_OR_LOCAL = [
    "http://127.0.0.1/",
    "http://localhost/",
    "http://0.0.0.0/",
    "http://[::1]/",
    "http://2130706433/",  # 127.0.0.1 as one decimal number
    "http://0x7f000001/",  # ... in hex
    "http://017700000001/",  # ... in octal
    "http://127.1/",  # shortened form
    "http://[::ffff:127.0.0.1]/",  # IPv4 hidden inside an IPv6 address
    "http://169.254.169.254/latest/meta-data/",  # cloud metadata service
    "http://[fd00:ec2::254]/",  # AWS IPv6 metadata address
    "http://10.0.0.1/",
    "http://172.16.0.1/",
    "http://192.168.1.1/",
    "http://100.64.0.1/",  # carrier-grade NAT range
    "http://user:pass@127.0.0.1/",  # credentials in the URL
    "http://127.0.0.1.nip.io/",  # a public DNS name that resolves to 127.0.0.1
]

NOT_HTTP = ["file:///etc/passwd", "gopher://127.0.0.1/", "ftp://example.com/", "javascript:alert(1)", "data:text/html,hi"]


@pytest.mark.parametrize("url", PRIVATE_OR_LOCAL)
async def test_private_and_local_addresses_are_blocked(url):
    with pytest.raises(PipelineError):
        await _ensure_public(url)


@pytest.mark.parametrize("url", NOT_HTTP)
async def test_non_http_schemes_are_blocked(url):
    with pytest.raises(PipelineError) as e:
        await _ensure_public(url)
    assert e.value.code == ErrorCode.INVALID_URL


@pytest.mark.parametrize("url", ["http://93.184.216.34/", "https://[2606:4700:4700::1111]/"])
async def test_public_addresses_are_allowed(url):
    await _ensure_public(url)  # must not raise: the guard should not over-block


@pytest.mark.parametrize("port", [22, 25, 3306, 5432, 6379, 9200])
async def test_unusual_ports_are_refused(port):
    """Otherwise the tool doubles as a port scanner: 'timed out' vs 'refused' vs 'HTTP 200' leaks what is open."""
    with pytest.raises(PipelineError):
        await _ensure_public(f"http://93.184.216.34:{port}/")
