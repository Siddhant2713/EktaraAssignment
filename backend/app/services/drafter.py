import logging
import re

from pydantic import BaseModel

from app.schemas.company import Company
from app import config
from app.schemas.draft import Fact, Opener, Person, Tone
from app.schemas.events import ErrorCode
from app.services.errors import PipelineError
from app.services.llm import generate_json

log = logging.getLogger(__name__)
STEP = "draft"

NUM_OPENERS = 3
TEMPERATURE = 0.8  # some variety between the openers; the research steps run at 0

SYSTEM_PROMPT = """You write the opening lines of a cold email, from a sender to one founder. The founder \\
gets many such emails every day and deletes most within seconds. Your openers must not sound like the rest.

Write {n} openers. Each one:
- is written to ONE founder from the list ("to"), and is built on ONE fact about that founder ("fact_ids"). \\
When there are enough facts, the {n} openers use {n} different facts.
- is 2 to 4 short sentences. No greeting ("Hi ...") and no sign-off: the rest of the email follows it.
- starts from the specific thing in the fact, in plain words, as something the sender noticed or thought about. \\
It is an observation, not praise.
- then connects it, honestly, to why the sender is writing, using the pitch. The link must be real. If a fact has \\
no natural link to the pitch, use another fact.
- ends on something that makes the reader want the next paragraph, such as a specific observation or a question \\
they would actually want to answer. It does not end on a request for a call.

Hard rules:
- Use only the facts provided. Never invent anything about the founder, the company or the sender. Never claim \\
more than the quote supports.
- Say nothing about the sender beyond what the pitch states. Do not claim the sender shares the founder's \
beliefs or principles ("I follow the same principle"), and do not add benefits or details the pitch does not give.
- Never pretend familiarity ("I've followed you for years", "loved your talk"). The sender has not said any such thing.
- No flattery or hype words (impressive, amazing, inspiring, incredible, game-changing). No congratulations. \\
No "I came across", "hope this finds you well", "huge fan", "reaching out", "quick call". No exclamation marks. \\
No em dashes. No emojis.
- The {n} openers must differ in shape, not only in topic. Do not start more than one of them with "You". \
For example, one can open with a question about the founder's own words, another with a short plain observation, \
another with a contrast between what they said and what most companies do.
- angle: 3 to 6 words naming the hook, for the sender's eyes only (e.g. "ignoring competitor trends").
{tone_rule}{fallback_rule}"""

TONE_RULES = {
    Tone.CASUAL: "\n- Tone: plain and conversational, like a note to a peer. Contractions are fine. No jargon.",
    Tone.FORMAL: "\n- Tone: polite and professional, full sentences, no slang.",
    Tone.SHORT: "\n- Tone: very short. At most 2 sentences and under 40 words.",
}

FALLBACK_RULE = """
- IMPORTANT: no personal facts about the founders could be found. Write the openers using ONLY the company \\
description and the pitch. Leave fact_ids empty and use "the company" as the angle. Do not pretend to know the \\
founder personally; make the observation about the company itself."""

# Phrases that mark a cold email as mass-produced. Checked in code because prompts alone get ignored.
BANNED = re.compile(
    r"hope (this|you)|i came across|i stumbled|[bh]uge fan|big fan|love what you|congrat|impressive|inspiring|"
    r"inspired by|amazing|incredible|game[- ]chang|revolution|passionate about|reaching out|reach out|"
    r"quick (question|call|chat)|pick your brain|synerg|touch base|my name is|i'?ve been following|"
    r"been following (you|your)|as a fellow|\bmost (\w+ ){0,2}(teams|companies|founders|startups|businesses|people|tools|products)\b",
    re.IGNORECASE,
)
GREETING = re.compile(r"^\s*(hi|hello|hey|dear)\b", re.IGNORECASE)
# a sentence that is clearly a question but ends in a full stop
UNMARKED_QUESTION = re.compile(
    r"^\s*((how|what|why|when|where|who|which)\b|(do|does|did|are|is|was|were|can|could|would|will|have|has)\s+"
    r"(you|your|they|the|it|we|this|that|there)\b)",
    re.IGNORECASE,
)


class DraftOutput(BaseModel):
    openers: list[Opener]


async def draft_openers(
    *, company: Company, founders: list[Person], pitch: str, tone: Tone, facts: list[Fact]
) -> list[Opener]:
    """Ask Gemini for openers, lint them, and retry once with the problems listed. Raises if none pass."""
    system_prompt = SYSTEM_PROMPT.format(
        n=NUM_OPENERS, tone_rule=TONE_RULES[tone], fallback_rule="" if facts else FALLBACK_RULE
    )
    base_prompt = _build_prompt(company, founders, pitch, facts)

    valid: list[Opener] = []
    problems: list[str] = []
    for attempt in range(2):
        prompt = base_prompt
        if problems:
            prompt += "\n\nYour previous attempt had these problems. Avoid them:\n" + "\n".join(f"- {p}" for p in problems)

        output = await generate_json(
            step=STEP,
            system_prompt=system_prompt,
            prompt=prompt,
            schema=DraftOutput,
            temperature=TEMPERATURE,
            model=config.GEMINI_DRAFT_MODEL,
        )
        problems = []
        for i, opener in enumerate(output.openers, start=1):
            found = lint(opener, tone=tone, founders=founders, facts=facts)
            if found:
                problems.append(f"opener {i}: " + "; ".join(found))
            elif all(opener.text != v.text for v in valid):
                valid.append(opener)

        if len(valid) >= NUM_OPENERS or (attempt == 0 and len(valid) >= 2):
            break
        log.info("draft attempt %d gave %d valid opener(s); problems: %s", attempt + 1, len(valid), problems)

    if not valid:
        raise PipelineError(STEP, ErrorCode.LLM_FAILED, "could not write an opener that passed the quality checks")
    return valid[:NUM_OPENERS]


def _build_prompt(company: Company, founders: list[Person], pitch: str, facts: list[Fact]) -> str:
    people = "\n".join(f"- {f.name}" + (f" ({f.role})" if f.role else "") for f in founders)
    if facts:
        fact_lines = "\n".join(f'[{f.id}] about {f.person}: {f.text}\n    source quote: "{f.quote}"' for f in facts)
    else:
        fact_lines = "(none found)"
    return (
        f"SENDER'S PITCH (what the sender sells or asks for; the only thing you know about the sender):\n{pitch}\n\n"
        f"COMPANY: {company.name}: {company.one_liner}\n\n"
        f"FOUNDERS (write each opener to ONE of them):\n{people}\n\n"
        f"FACTS (verified, each from a public source; use only these and refer to them by id):\n{fact_lines}"
    )


def lint(opener: Opener, *, tone: Tone, founders: list[Person], facts: list[Fact]) -> list[str]:
    """Return what is wrong with an opener (an empty list means it passes)."""
    problems = []
    text = opener.text.strip()

    recipient = next((f for f in founders if f.name.lower() == opener.to.strip().lower()), None)
    if recipient is None:
        problems.append(f'"to" must be one of the founders, got {opener.to!r}')

    if not text:
        return problems + ["empty text"]
    if hit := BANNED.search(text):
        problems.append(f"uses the cliché {hit.group(0)!r}")
    if "!" in text:
        problems.append("has an exclamation mark")
    if "—" in text or "–" in text:
        problems.append("has a dash used as punctuation")
    if GREETING.match(text):
        problems.append("starts with a greeting")

    if any(s.rstrip().endswith(".") and UNMARKED_QUESTION.match(s) for s in re.split(r"(?<=[.!?])\s+", text)):
        problems.append("a question ends with a full stop instead of a question mark")

    sentences = len(re.findall(r"[.!?](?:\s|$)", text))
    words = len(text.split())
    max_sentences, max_words = (2, 45) if tone == Tone.SHORT else (5, 90)
    if sentences < 1 or sentences > max_sentences or words > max_words:
        problems.append(f"length is off ({sentences} sentences, {words} words; limit {max_sentences} and {max_words})")

    allowed = {f.id for f in facts if recipient and f.person.lower() == recipient.name.lower()}
    if facts and allowed and not opener.fact_ids:
        problems.append("does not say which fact it is built on")
    if any(fid not in allowed for fid in opener.fact_ids):
        problems.append("cites a fact id that does not exist for this founder")
    return problems
