"""AI-assisted job description drafting.

Two editorial tools: rewrite an existing description, and generate one from the
structured fields an editor has already filled in.

**Nothing here writes to the database.** Every call returns a draft the admin
reviews side by side and explicitly accepts. That is a product requirement, and
it is also the honest engineering position: a model that occasionally invents a
benefit or softens a requirement must not be able to publish that unreviewed.

**Structured output, not prose parsing.** Both tools return a schema-validated
object rather than markdown the client has to split on headings. Asking a model
for "a description, then a Responsibilities section" and parsing the result is
a contract that breaks the first time the model formats a heading differently.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

import anthropic
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.exceptions import DomainError

logger = logging.getLogger(__name__)


class AIUnavailable(DomainError):
    status = 503
    code = "ai_unavailable"
    title = "AI assistance is not configured"


class AIFailed(DomainError):
    status = 502
    code = "ai_failed"
    title = "The AI service could not complete this request"


class AIRefused(DomainError):
    """The model declined the request.

    Surfaced distinctly from a failure: a refusal is a decision about the
    content, and telling an editor "try again" would send them into a loop.
    """

    status = 422
    code = "ai_refused"
    title = "The assistant declined this request"


# --- output contract ------------------------------------------------------


class JobContent(BaseModel):
    """What both tools return.

    The same shape either way, so the review UI has one thing to render and the
    accept path has one thing to apply.
    """

    description: str = Field(
        description=(
            "The role summary in flowing prose, 2-4 paragraphs, at least 50 "
            "characters. No headings, no bullet points, no markdown."
        )
    )
    responsibilities: list[str] = Field(
        description="What the person will do. Each item one short sentence, no leading bullet."
    )
    requirements: list[str] = Field(
        description="What the candidate must bring. Each item one short phrase or sentence."
    )
    benefits: list[str] = Field(
        description=(
            "What the employer offers. Empty list when the source material "
            "mentions none — never invent compensation or perks."
        )
    )
    apply_note: str = Field(
        description=(
            "One or two sentences telling the candidate how to apply and what "
            "to expect. Never invent a deadline, an email address or a URL."
        )
    )


#: The shared operating rules. Kept first and byte-stable across every request
#: so the cached prefix is reused — see the caching note on `_client`.
_SYSTEM = """You are an editorial assistant for Rozgar.pk, a Pakistani job board. You \
prepare job listings that will be read by candidates in Pakistan.

House style:
- Plain, direct English. Short sentences. No marketing superlatives, no "rockstar", \
no "ninja", no "we're like a family".
- Address the candidate as "you". Refer to the employer by name or as "the team".
- Keep Pakistani market conventions: PKR salaries, local city names, and terms like \
"fresh graduate" and "notice period" as written.
- Urdu or Arabic-script text in the source is left in that script, not transliterated.

Absolute rules:
- Never invent a fact. No salary, benefit, deadline, contact address, team size, \
funding, or technology that is not in the material you were given.
- If information is missing, leave the corresponding field empty rather than filling it.
- Never contradict the structured fields you were given.
"""

_REWRITE_INSTRUCTIONS = """Rewrite the job description below.

What to change:
- Fix grammar, spelling and punctuation.
- Remove duplicated wording and redundant sentences.
- Improve readability: shorter sentences, clearer paragraph breaks, logical order.
- Apply the house style above.

What must not change:
- The meaning. Every fact, requirement, skill, salary figure, location and \
condition in the original must survive the rewrite unchanged.
- The seniority and scope of the role.
- Anything you would have to guess at. If a sentence is unclear, keep its \
meaning rather than resolving the ambiguity yourself.

Return the rewritten description, and split any responsibilities, requirements \
and benefits that were embedded in the prose into their own lists. Do not add \
items that were not there.
"""

_GENERATE_INSTRUCTIONS = """Write a job description from the structured details below.

Ground every sentence in those details. Where a detail is absent — no salary, no \
skills listed — write around it rather than inventing one; an empty benefits list \
is the correct output for a listing that mentions no benefits.

Length: enough to tell a candidate what the job is and whether they qualify. Two \
to four paragraphs of description, then the lists.
"""


@dataclass(frozen=True)
class JobFacts:
    """The structured fields an editor has already filled in."""

    title: str
    company: str
    location: str
    employment_type: str
    experience_level: str
    salary: str | None = None
    skills: tuple[str, ...] = ()

    def as_prompt(self) -> str:
        lines = [
            f"Job title: {self.title}",
            f"Company: {self.company}",
            f"Location: {self.location}",
            f"Employment type: {self.employment_type}",
            f"Experience level: {self.experience_level}",
        ]
        if self.salary:
            lines.append(f"Salary: {self.salary}")
        else:
            lines.append("Salary: not disclosed by the employer")
        if self.skills:
            lines.append(f"Skills required: {', '.join(self.skills)}")
        else:
            lines.append("Skills required: none specified")
        return "\n".join(lines)


_client: anthropic.AsyncAnthropic | None = None


def get_client() -> anthropic.AsyncAnthropic:
    """One client for the process.

    Built once so the underlying HTTP connection pool is reused; rebuilding it
    per request would add a TLS handshake to every call.
    """
    global _client
    if not settings.anthropic_api_key:
        raise AIUnavailable(
            "AI assistance is not configured on this server. Set ANTHROPIC_API_KEY to enable it."
        )
    if _client is None:
        _client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _client


def reset_client() -> None:
    """Drop the cached client. Used by tests, and after a key rotation."""
    global _client
    _client = None


class AIService:
    """The two editorial tools.

    Deliberately has no session and no repository: it reads nothing and writes
    nothing. Everything it produces goes back to the admin for review.
    """

    async def rewrite(self, description: str) -> JobContent:
        if len(description.strip()) < 40:
            raise AIFailed(
                "There is not enough text to rewrite. Write a rough draft first — "
                "even a few sentences is enough to work from."
            )
        return await self._draft(
            f"{_REWRITE_INSTRUCTIONS}\n\n<description>\n{description.strip()}\n</description>",
            mode="rewrite",
        )

    async def generate(self, facts: JobFacts) -> JobContent:
        return await self._draft(
            f"{_GENERATE_INSTRUCTIONS}\n\n<job_details>\n{facts.as_prompt()}\n</job_details>",
            mode="generate",
        )

    async def _draft(self, instruction: str, *, mode: Literal["rewrite", "generate"]) -> JobContent:
        client = get_client()
        try:
            # `.parse()` validates the response against the schema and retries
            # the model on a mismatch, so the caller never has to handle
            # half-valid JSON.
            #
            # The system prompt is a stable prefix and carries the cache
            # breakpoint; the per-request instruction follows it, so repeated
            # calls reuse the cached rules.
            message = await client.messages.parse(
                model=settings.ai_model,
                max_tokens=settings.ai_max_tokens,
                system=[
                    {
                        "type": "text",
                        "text": _SYSTEM,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                # Adaptive thinking: rewriting without changing meaning is a
                # judgement task, and the model decides how much deliberation
                # each listing needs.
                thinking={"type": "adaptive"},
                # `output_format` takes the model class on `.parse()`;
                # `output_config` carries effort. Medium is the right tier here:
                # this is editing, not open-ended reasoning, and higher effort
                # spends tokens deliberating over sentence order.
                output_format=JobContent,
                output_config={"effort": "medium"},
                messages=[{"role": "user", "content": instruction}],
            )
        except anthropic.APIStatusError as exc:
            logger.warning(
                "anthropic api error",
                extra={"event": "ai.api_error", "mode": mode, "status": exc.status_code},
            )
            if exc.status_code == 429:
                raise AIFailed("The AI service is rate limited. Try again shortly.") from exc
            raise AIFailed("The AI service returned an error. Try again.") from exc
        except anthropic.APIConnectionError as exc:
            logger.warning("anthropic unreachable", extra={"event": "ai.unreachable", "mode": mode})
            raise AIFailed("Could not reach the AI service.") from exc

        # Checked before touching `content` — on a refusal the parsed output is
        # absent and indexing it would raise something unrelated to the cause.
        if message.stop_reason == "refusal":
            logger.info(
                "anthropic refused",
                extra={
                    "event": "ai.refused",
                    "mode": mode,
                    "category": getattr(message.stop_details, "category", None),
                },
            )
            raise AIRefused(
                "The assistant declined to work on this text. Edit the wording and try again."
            )

        if message.stop_reason == "max_tokens":
            raise AIFailed("The draft was cut short. Try again with a shorter source description.")

        parsed = message.parsed_output
        if parsed is None:
            raise AIFailed("The AI service returned an unusable response. Try again.")

        logger.info(
            "ai draft produced",
            extra={
                "event": "ai.drafted",
                "mode": mode,
                "input_tokens": message.usage.input_tokens,
                "output_tokens": message.usage.output_tokens,
                "cache_read": message.usage.cache_read_input_tokens,
            },
        )
        return parsed


__all__ = ["AIFailed", "AIRefused", "AIService", "AIUnavailable", "JobContent", "JobFacts"]
