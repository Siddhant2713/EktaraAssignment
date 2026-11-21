"""Accuracy on real companies: does founder extraction find the right people and avoid the wrong ones?

Run with `pytest --live`. Needs network and a working Gemini key. Upstream trouble skips a case instead of failing it.
"""

import pytest

from app.services.analyzer import analyze
from tests.live.helpers import upstream_trouble
from tests.support.helpers import collect, terminal

pytestmark = [pytest.mark.live, pytest.mark.timeout(150)]

# (url, last names that must be found, full names that must NOT appear, why this case is hard)
GOLDEN = [
    ("https://basecamp.com", ["Fried"], [], "founder named on the site"),
    ("https://plausible.io", ["Täht", "Saric"], [], "names only in structured data and a signature"),
    ("https://buttondown.com", ["Duke"], [], "solo founder named in structured data"),
    ("https://dub.co", ["Tey"], ["Johnny Ho"], "testimonial from another company's co-founder"),
    ("https://tally.so", ["Martens", "Minev"], ["Shyam Sunder Goenka", "Bharat Goenka"], "namesake company (Tally Solutions)"),
    ("https://www.spacex.com", ["Musk"], [], "site is JavaScript-only; needs web search"),
    ("https://paytm.com", ["Sharma"], [], "site does not name the founder"),
    ("https://www.tesla.com", ["Musk"], [], "site blocks scrapers (HTTP 403)"),
]


@pytest.mark.parametrize("url, must_find, must_not_find, why", GOLDEN, ids=[g[0].split("//")[1] for g in GOLDEN])
async def test_founder_extraction(url, must_find, must_not_find, why):
    events = await collect(analyze(url))
    end = terminal(events)[0]
    names = [f["name"] for f in end.data["founders"]] if end.type == "result" else []
    joined = " | ".join(names)
    missing = [n for n in must_find if n.lower() not in joined.lower()]
    wrong = [n for n in must_not_find if n.lower() in joined.lower()]

    if (end.type == "error" or missing) and (reason := upstream_trouble(events)):
        pytest.skip(f"upstream unavailable: {reason[:90]}")
    assert end.type == "result", f"{why}: {end.message}"
    assert not missing, f"missed {missing} ({why}); got {names}"
    assert not wrong, f"wrongly included {wrong} ({why}); got {names}"
