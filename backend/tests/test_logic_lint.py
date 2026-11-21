"""The drafter's quality gate: what counts as an opener we are willing to show."""

import pytest

from app.schemas.draft import Fact, Opener, Person, Tone
from app.services.drafter import lint

FOUNDERS = [Person(name="Jason Fried", role="CEO"), Person(name="Ana Lee")]


def make_fact(id, person):
    return Fact(id=id, person=person, text="t", quote="q", source_url="u", source_title="s", kind="own_words", specificity=5, date=None)


FACTS = [make_fact(1, "Jason Fried"), make_fact(2, "Ana Lee")]
GOOD = "You said you stay ignorant about competitors on purpose. We built our tool the same way, with no benchmarking. Do you ever regret not looking?"


def opener(text, to="Jason Fried", ids=(1,)):
    return Opener(to=to, text=text, fact_ids=list(ids), angle="x")


def problems(o, tone=Tone.CASUAL, facts=FACTS):
    return lint(o, tone=tone, founders=FOUNDERS, facts=facts)


def test_a_good_opener_passes():
    assert problems(opener(GOOD)) == []


@pytest.mark.parametrize(
    "text, expected",
    [
        ("I came across your podcast. " + GOOD, "cliché"),
        ("Your work is impressive. We build X. Want to talk?", "cliché"),
        ("Hope this finds you well. " + GOOD, "cliché"),
        ("You ignore trends. Most internal tools interrupt focus. We help. Why?", "cliché"),
        ("You ignore trends. Most teams use meetings. We help. Why?", "cliché"),
        (GOOD + " Wow!", "exclamation"),
        ("You ignore competitors — on purpose. We do too. Why?", "dash"),
        ("Hi Jason, " + GOOD, "greeting"),
        ("Too short", "length"),
        ("You ignore trends on purpose. How do you decide what to build.", "question mark"),
        ("You ignore trends on purpose. Does your team track morale.", "question mark"),
    ],
)
def test_lint_rejects(text, expected):
    assert any(expected in p for p in problems(opener(text))), problems(opener(text))


def test_short_tone_has_a_tighter_limit():
    assert any("length" in p for p in problems(opener(GOOD), tone=Tone.SHORT))


def test_too_many_sentences_is_rejected():
    assert any("length" in p for p in problems(opener(" ".join(["Word."] * 8))))


def test_imperative_sentences_are_not_mistaken_for_questions():
    assert problems(opener("You ignore trends on purpose. Do not mistake that for luck. We build tools for that.")) == []


def test_opener_must_say_which_fact_it_uses():
    assert any("which fact" in p for p in problems(opener(GOOD, ids=())))


def test_opener_cannot_cite_another_founders_fact_or_a_missing_one():
    assert any("fact id" in p for p in problems(opener(GOOD, ids=(2,))))
    assert any("fact id" in p for p in problems(opener(GOOD, ids=(9,))))


def test_recipient_must_be_one_of_the_founders():
    assert any('"to"' in p for p in problems(opener(GOOD, to="Someone Else")))


def test_fallback_mode_needs_no_fact_ids_and_forbids_them():
    assert problems(opener(GOOD, ids=()), facts=[]) == []
    assert any("fact id" in p for p in problems(opener(GOOD, ids=(1,)), facts=[]))


def test_empty_text_is_rejected_without_crashing():
    assert problems(opener("   "))
