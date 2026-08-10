import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class EvidenceItem(BaseModel):
    model_config = ConfigDict(extra="allow")
    field: str
    evidence: str
    page: int | None = None


class CandidateProfile(BaseModel):
    model_config = ConfigDict(extra="allow")
    full_name: str | None = None
    summary: str = ""
    skills: list[str | dict[str, Any]] = Field(default_factory=list)
    experience: list[str | dict[str, Any]] = Field(default_factory=list)
    education: list[str | dict[str, Any]] = Field(default_factory=list)
    certifications: list[str | dict[str, Any]] = Field(default_factory=list)
    projects: list[str | dict[str, Any]] = Field(default_factory=list)
    languages: list[str | dict[str, Any]] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    source_evidence: list[EvidenceItem | dict[str, Any] | str] = Field(default_factory=list)


def normalize_candidate_profile_json(content: str) -> str:
    candidate = content.strip()
    if candidate.startswith("```"):
        lines = candidate.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        candidate = "\n".join(lines)
    if not candidate.lstrip().startswith("{"):
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start >= 0 and end > start:
            candidate = candidate[start:end + 1]
    try:
        parsed = json.loads(candidate)
        profile = CandidateProfile.model_validate(parsed)
    except (json.JSONDecodeError, ValidationError) as exc:
        raise ValueError("CandidateProfile output is not valid schema-compliant JSON") from exc
    return json.dumps(profile.model_dump(), ensure_ascii=False, indent=2)


CANDIDATE_PROFILE_SCHEMA = {
    "type": "object",
    "properties": {
        "full_name": {"type": ["string", "null"]},
        "summary": {"type": "string"},
        "skills": {"type": "array"},
        "experience": {"type": "array"},
        "education": {"type": "array"},
        "certifications": {"type": "array", "items": {"type": ["string", "object"]}},
        "projects": {"type": "array", "items": {"type": ["string", "object"]}},
        "languages": {"type": "array", "items": {"type": ["string", "object"]}},
        "missing_information": {"type": "array", "items": {"type": "string"}},
        "source_evidence": {"type": "array"},
    },
}

CANDIDATE_PROFILE_INSTRUCTIONS = """When a PDF CV is attached, call pdf_to_text before answering.
Extract only facts supported by the CV and return one valid JSON object matching the expected schema.
Do not score, rank, recommend, accept, or reject the candidate.
Do not infer missing facts. Put absent or unclear job-relevant information in missing_information.
Exclude age/date of birth, gender, photograph, marital/family status, disability, ethnicity, religion,
nationality and other protected or sensitive attributes from the profile.
Keep evidence short and identify the source page when the page marker makes it available.
Do not wrap the JSON in Markdown fences and do not add prose before or after it."""

CANDIDATE_PROFILE_DESCRIPTION = (
    "Extract a structured, evidence-based CandidateProfile JSON from an attached CV without scoring it."
)
