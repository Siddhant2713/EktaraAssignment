"""Founder and fact verification: the code that decides whether a claim from the LLM is believed."""

from app.schemas.company import Company
from app.schemas.draft import Fact, Person
from app.schemas.scrape import ScrapedPage
from app.services.extractor import ExtractedPerson, verified_founders
from app.services.fact_extractor import SENSITIVE, ExtractedFact, select_facts, verify_facts
from app.services.textmatch import has_word, norm


def person(name, rel, evidence, role="Co-founder"):
    return ExtractedPerson(name=name, role=role, relationship=rel, confidence=0.9, evidence=evidence)


PAGES = [
    ScrapedPage(url="https://x.com/", title="", text="“It’s great,” Johnny Ho Co-founder at Perplexity. Thanks, Uku and Marko Co-founders"),
    ScrapedPage(url="https://x.com/about", title="", text="Jane Roe is our CEO &amp; builder. Sam Lee, Founder. Uku Taht, Co-founder of X."),
]


def names(people, pages=PAGES, source="site"):
    return [f.name for f in verified_founders(people, pages, source)]


# ---------- founders ----------

def test_testimonial_author_labelled_other_company_is_excluded():
    assert names([person("Johnny Ho", "other_company", "Johnny Ho Co-founder at Perplexity")]) == []


def test_invented_quote_is_dropped():
    assert names([person("Sam Lee", "founder", "Sam Lee founded this company in 2019")]) == []


def test_quote_that_does_not_mention_the_person_is_dropped():
    assert names([person("Sam Lee", "founder", "Jane Roe is our CEO")]) == []


def test_entities_quotes_and_case_are_tolerated_and_source_is_where_quote_was_found():
    found = verified_founders([person("Jane Roe", "ceo", "JANE ROE is our CEO & builder", role="CEO")], PAGES, "site")
    assert [f.name for f in found] == ["Jane Roe"]
    assert found[0].source_url == "https://x.com/about"


def test_bare_first_name_is_merged_into_the_full_name():
    got = names([
        person("Uku", "cofounder", "Uku and Marko Co-founders"),
        person("Marko", "cofounder", "Uku and Marko Co-founders"),
        person("Uku Taht", "cofounder", "Uku Taht, Co-founder of X"),
    ])
    assert got == ["Marko", "Uku Taht"]


def test_founders_are_listed_before_ceos():
    got = names([person("Jane Roe", "ceo", "Jane Roe is our CEO"), person("Sam Lee", "founder", "Sam Lee, Founder")])
    assert got == ["Sam Lee", "Jane Roe"]


def test_quote_may_use_first_name_only_when_full_name_is_elsewhere():
    pages = [
        ScrapedPage(url="https://a.com/", title="", text="Hello! I’m Marie, co-founder of Tally."),
        ScrapedPage(url="https://b.com/", title="", text="Marie Martens and Filip Minev started Tally in summer 2020"),
    ]
    assert names([person("Marie Martens", "cofounder", "Hello! I'm Marie, co-founder of Tally.")], pages) == ["Marie Martens"]


def test_quote_about_someone_else_does_not_vouch_for_a_name_found_elsewhere():
    pages = [
        ScrapedPage(url="https://a.com/", title="", text="Hello! I’m Marie, co-founder of Tally."),
        ScrapedPage(url="https://b.com/", title="", text="Marie Martens and Filip Minev started Tally in summer 2020"),
    ]
    assert names([person("Filip Minev", "cofounder", "Hello! I'm Marie, co-founder of Tally.")], pages) == []


def test_names_match_whole_words_only():
    pages = [ScrapedPage(url="https://c.com/", title="", text="Samuel Jones, Founder")]
    assert names([person("Sam Jones", "founder", "Samuel Jones, Founder")], pages) == []


def test_initials_with_dots_work():
    pages = [ScrapedPage(url="https://d.com/", title="", text="J.B. Straubel, co-founder of Tesla")]
    assert names([person("J.B. Straubel", "cofounder", "J.B. Straubel, co-founder of Tesla")], pages) == ["J.B. Straubel"]


def test_web_source_is_recorded():
    pages = [ScrapedPage(url="https://w.com/", title="", text="SpaceX was founded in 2002 by Elon Musk")]
    found = verified_founders([person("Elon Musk", "founder", "SpaceX was founded in 2002 by Elon Musk")], pages, "web")
    assert [(f.name, f.source) for f in found] == [("Elon Musk", "web")]


def test_empty_name_or_empty_evidence_is_dropped():
    assert names([person("", "founder", "Jane Roe is our CEO")]) == []
    assert names([person("Jane Roe", "founder", "")]) == []


def test_confidence_is_clamped_to_0_1():
    p = ExtractedPerson(name="Jane Roe", role=None, relationship="ceo", confidence=7.5, evidence="Jane Roe is our CEO")
    assert verified_founders([p], PAGES, "site")[0].confidence == 1.0


# ---------- facts ----------

COMPANY = Company(name="Basecamp", one_liner="Basecamp is a project management platform.")
JASON = Person(name="Jason Fried", role="CEO")
GOOD_QUOTE = "I try to be quite ignorant actually about the trends in the industry and who is doing what."
FACT_PAGES = [
    ScrapedPage(url="https://pod.example/jason", title="Podcast", text=f"Jason Fried of Basecamp said: {GOOD_QUOTE}"),
    ScrapedPage(url="https://other.example/jason", title="Namesake", text="Jason Fried the dentist loves teeth. He said: I floss every day without exception."),
]


def ef(quote, text="a fact", kind="own_words", spec=5, date=None):
    return ExtractedFact(text=text, quote=quote, kind=kind, specificity=spec, date=date)


def verify(*facts):
    return verify_facts(list(facts), FACT_PAGES, JASON, COMPANY, "basecamp.com")


def test_fact_with_quote_on_a_page_about_the_person_and_company_is_kept():
    assert [f.source_url for f in verify(ef(GOOD_QUOTE))] == ["https://pod.example/jason"]


def test_fact_from_a_namesake_page_is_dropped():
    assert verify(ef("I floss every day without exception.")) == []


def test_fact_with_invented_quote_is_dropped():
    assert verify(ef("I never read email before noon and neither should you.")) == []


def test_short_quote_is_dropped():
    assert verify(ef("I try to be quite")) == []


def test_duplicate_quotes_are_collapsed():
    assert len(verify(ef(GOOD_QUOTE), ef(GOOD_QUOTE, text="same quote again"))) == 1


def test_sensitive_topics_are_dropped_even_when_the_quote_is_real():
    pages = [ScrapedPage(url="https://p.example/", title="", text="Jason Fried of Basecamp said: I lean on my wife a lot for advice about the business.")]
    got = verify_facts([ef("I lean on my wife a lot for advice about the business.", text="He relies on his wife")], pages, JASON, COMPANY, "basecamp.com")
    assert got == []


def test_sensitive_filter_matches_whole_words_and_over_matches_on_purpose():
    for text in ["I lean on my wife a lot", "his daughter was born", "diagnosed with cancer", "Masayoshi Son founded"]:
        assert SENSITIVE.search(norm(text)), text
    for text in ["We secured five enterprise clients", "a sonic boom of growth", "the sonnet app", "mentoring other founders"]:
        assert not SENSITIVE.search(norm(text)), text


def fact(id, spec, kind, date=None, quote="q"):
    return Fact(id=id, person="P", text="t", quote=quote, source_url="u", source_title="s", kind=kind, specificity=spec, date=date)


def test_select_facts_prefers_specific_then_own_words_then_recent():
    facts = [
        fact(1, 3, "own_words"),
        fact(2, 5, "milestone"),
        fact(3, 5, "own_words", date="2019"),
        fact(4, 5, "own_words", date="2025"),
    ]
    assert [f.id for f in select_facts(facts, 4)] == [4, 3, 2, 1]
    assert [f.id for f in select_facts(facts, 2)] == [4, 3]


def test_has_word_edge_cases():
    assert has_word("hello world", "world")
    assert not has_word("helloworld", "world")
    assert has_word("j.b. straubel", "j.b.")
    has_word("anything", "")  # must not raise


# ---------- accents ----------

def test_spellings_that_differ_only_by_accents_are_one_person():
    pages = [ScrapedPage(url="https://p.example/", title="", text="Uku Täht, Co-founder. Elsewhere on the page: Uku Taht, Co-founder.")]
    got = names([person("Uku Täht", "cofounder", "Uku Täht, Co-founder"), person("Uku Taht", "cofounder", "Uku Taht, Co-founder")], pages)
    assert len(got) == 1, got


def test_a_quote_without_accents_still_verifies_a_name_with_them():
    pages = [ScrapedPage(url="https://p.example/", title="", text="Uku Taht, Co-founder of Plausible")]
    assert names([person("Uku Täht", "cofounder", "Uku Taht, Co-founder of Plausible")], pages) == ["Uku Täht"]


def test_norm_leaves_non_latin_text_comparable():
    assert norm("山田 太郎") == norm("山田  太郎") and norm("Zoë") == norm("ZOE")
