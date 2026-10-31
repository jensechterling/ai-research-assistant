"""One structured Melious call per article: prompt, validation, repair, truncation."""
import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from src.config import get_project_dir
from src.extraction import ExtractedArticle
from src.llm import FatalRunError, LLMError

MODEL_MAX_OUTPUT_TOKENS = 32000
_PROMPTS = Environment(
    loader=FileSystemLoader(str(get_project_dir() / "templates" / "prompts")),
    keep_trailing_newline=True,
)


class Analysis(BaseModel):
    """The model's analysis of one article."""

    model_config = ConfigDict(extra="ignore")

    summary: str = Field(min_length=1, description="2-3 paragraphs separated by a blank line")
    key_findings: list[str] = Field(min_length=1, max_length=12, description="5-10 key findings")
    suggestions_work: list[str] = Field(min_length=1, max_length=6, description="3-5 work suggestions")
    suggestions_personal: list[str] = Field(min_length=1, max_length=6, description="3-5 personal suggestions")
    tags: list[str] = Field(max_length=5, description="Up to 5 lower-case hyphenated topical tags")
    kb_folder: str = Field(min_length=1, description="Knowledge-base folder name")
    takeaway: str = Field(min_length=1, description="One-line key insight")
    action: str = Field(min_length=1, description="One-line specific action")

    @field_validator("tags")
    @classmethod
    def _normalise_tags(cls, tags: list[str]) -> list[str]:
        normalised = []
        for tag in tags:
            tag = re.sub(r"[\s_]+", "-", tag.strip().lstrip("#").lower())
            tag = re.sub(r"[^a-z0-9/-]", "", tag).strip("-")
            if tag and tag not in normalised:
                normalised.append(tag)
        return normalised


@dataclass
class AnalysisContext:
    """Inputs shared by every article in a run."""

    profile: str
    folders: list[str]
    language: str
    today: date


@dataclass
class AnalysisResult:
    analysis: Analysis
    cost_eur: float


class AnalysisError(Exception):
    """Transient analysis failure, carrying the cost already spent."""

    def __init__(self, reason: str, cost_eur: float):
        super().__init__(reason)
        self.cost_eur = cost_eur


def load_context(config: dict, vault_path: Path, today: date) -> AnalysisContext:
    """Read the interest profile and list the top-level knowledge-base folders."""
    profile_path = vault_path / config["profile"]["interest_profile"]
    if not profile_path.is_file():
        raise FatalRunError(f"Interest profile not found: {profile_path}")

    kb_path = vault_path / config["folders"]["knowledge_base"]
    if not kb_path.is_dir():
        raise FatalRunError(f"Knowledge-base folder not found: {kb_path}")

    folders = sorted(p.name for p in kb_path.iterdir() if p.is_dir() and not p.name.startswith("."))
    return AnalysisContext(
        profile=profile_path.read_text(),
        folders=folders,
        language=config["llm"]["output_language"],
        today=today,
    )


def build_messages(article: ExtractedArticle, context: AnalysisContext) -> list[dict]:
    """Return [system, user] messages; the system message is the same for every article."""
    system = _PROMPTS.get_template("analysis-system.md.j2").render(
        language=context.language,
        schema=json.dumps(Analysis.model_json_schema(), indent=2),
        folders=context.folders,
        profile=context.profile,
    )
    user = _PROMPTS.get_template("analysis-user.md.j2").render(article=article)
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def analyze(article: ExtractedArticle, context: AnalysisContext, client, max_tokens: int) -> AnalysisResult:
    """Analyze one article; raises AnalysisError (transient) or FatalRunError."""
    messages = build_messages(article, context)
    cost = 0.0

    def request(msgs: list[dict], budget: int):
        nonlocal cost
        try:
            completion = client.complete(msgs, max_tokens=budget)
        except LLMError as e:
            raise AnalysisError(str(e), cost) from None
        cost += completion.usage.cost_eur
        return completion

    completion = request(messages, max_tokens)
    budget = max_tokens
    if completion.finish_reason == "length":
        budget = min(max_tokens * 2, MODEL_MAX_OUTPUT_TOKENS)
        completion = request(messages, budget)
        if completion.finish_reason == "length":
            raise AnalysisError("output truncated", cost)

    analysis, error = _validate(completion.content)
    if analysis is not None:
        return AnalysisResult(analysis, cost)

    repair = messages + [
        {"role": "assistant", "content": completion.content},
        {
            "role": "user",
            "content": f"Your reply was not valid: {error}\nReply again with only the corrected JSON object.",
        },
    ]
    completion = request(repair, budget)
    if completion.finish_reason == "length":
        raise AnalysisError("output truncated", cost)
    analysis, error = _validate(completion.content)
    if analysis is None:
        raise AnalysisError(f"invalid reply after repair: {error}", cost)
    return AnalysisResult(analysis, cost)


def _validate(content: str) -> tuple[Analysis | None, str | None]:
    try:
        return Analysis.model_validate(json.loads(content)), None
    except json.JSONDecodeError as e:
        return None, f"not valid JSON ({e.msg})"
    except ValidationError as e:
        return None, "; ".join(f"{'.'.join(map(str, err['loc']))}: {err['msg']}" for err in e.errors())[:500]
