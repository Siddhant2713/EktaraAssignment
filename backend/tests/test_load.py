"""Load: a burst of concurrent requests against a fast fake Gemini, a fast fake search and a local site.

The upstream services are faked on purpose: this measures OUR code (event loop, threads, memory, limits), not Google's
or DuckDuckGo's. Numbers are printed (run with -s or -rP) and the assertions state the limits we want.
"""

import asyncio
import resource
import time

import pytest

from app.services.analyzer import analyze
from tests.support.fakes import extraction_json
from tests.support.helpers import collect, terminal

MAX_GEMINI_AT_ONCE = 8  # more than this in flight and a real key gets 429s
MAX_SEARCH_AT_ONCE = 3  # the keyless search backend rate-limits almost immediately


async def lag_monitor(stop: asyncio.Event, lags: list[float]):
    """How late does a 50 ms timer fire? Large lag means something is blocking the event loop."""
    while not stop.is_set():
        started = time.monotonic()
        await asyncio.sleep(0.05)
        lags.append(time.monotonic() - started - 0.05)


def percentile(values, p):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(len(ordered) * p))]


async def run_burst(url: str, n: int):
    stop, lags = asyncio.Event(), []
    monitor = asyncio.create_task(lag_monitor(stop, lags))
    rss_before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss

    async def one():
        started = time.monotonic()
        events = await collect(analyze(url))
        return time.monotonic() - started, events

    started = time.monotonic()
    runs = await asyncio.gather(*(one() for _ in range(n)))
    wall = time.monotonic() - started
    stop.set()
    await monitor

    rss_growth_mb = (resource.getrusage(resource.RUSAGE_SELF).ru_maxrss - rss_before) / 1024
    return runs, wall, lags, rss_growth_mb


def report(capsys, title, n, runs, wall, lags, rss_mb, fake_gemini, fake_search):
    latencies = [r[0] for r in runs]
    ok = sum(1 for _, ev in runs if terminal(ev) and terminal(ev)[0].type == "result")
    with capsys.disabled():
        print(f"\n--- {title}: {n} concurrent requests")
        print(f"    succeeded {ok}/{n}   wall {wall:.1f}s   latency p50 {percentile(latencies, .5):.1f}s  p95 {percentile(latencies, .95):.1f}s  max {max(latencies):.1f}s")
        print(f"    peak concurrent Gemini calls {fake_gemini.max_in_flight}   peak concurrent searches {fake_search.max_in_flight}")
        print(f"    worst event-loop lag {max(lags) * 1000:.0f} ms   memory growth {rss_mb:.0f} MB")
    return ok


@pytest.mark.slow
async def test_burst_where_the_site_names_the_founder(hostile, allow_local, fake_gemini, fake_search, capsys):
    n = 60
    fake_gemini.latency = 0.3
    runs, wall, lags, rss = await run_burst(hostile.base + "/", n)
    ok = report(capsys, "site path", n, runs, wall, lags, rss, fake_gemini, fake_search)

    assert ok == n, f"only {ok}/{n} requests succeeded"
    assert fake_gemini.max_in_flight <= MAX_GEMINI_AT_ONCE, f"{fake_gemini.max_in_flight} simultaneous Gemini calls: no concurrency limit"
    assert max(lags) < 1.0, f"event loop stalled for {max(lags):.1f}s: something blocks it"
    assert percentile([r[0] for r in runs], 0.95) < 15


@pytest.mark.slow
async def test_burst_where_every_request_needs_the_web_fallback(hostile, allow_local, fake_gemini, fake_search, capsys):
    n = 40
    fake_gemini.latency = 0.3
    fake_search.latency = 0.2
    web_answer = extraction_json("Jane Roe founded Acme in 2020")
    no_founder_on_site = extraction_json(people=False)
    fake_gemini.default = lambda contents, cfg: web_answer if "### RESULT:" in contents else no_founder_on_site

    runs, wall, lags, rss = await run_burst(hostile.base + "/", n)
    ok = report(capsys, "web fallback path", n, runs, wall, lags, rss, fake_gemini, fake_search)

    assert ok == n, f"only {ok}/{n} requests succeeded"
    assert fake_search.max_in_flight <= MAX_SEARCH_AT_ONCE, f"{fake_search.max_in_flight} simultaneous searches: no concurrency limit"
    assert fake_gemini.max_in_flight <= MAX_GEMINI_AT_ONCE
    assert max(lags) < 1.0


async def test_no_task_is_left_running_after_a_burst(hostile, allow_local, fake_gemini, fake_search):
    """After the requests finish nothing from our code should still be running in the background."""
    before = {t for t in asyncio.all_tasks()}
    await run_burst(hostile.base + "/", 10)
    await asyncio.sleep(0.2)
    leftover = {t for t in asyncio.all_tasks()} - before
    assert not leftover, f"{len(leftover)} task(s) still running after all requests completed"
