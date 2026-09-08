from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class MetadataModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ExamStandardOut(MetadataModel):
    id: int
    code: str
    name: str
    description: str | None = None
    status: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExamSpecificationOut(MetadataModel):
    id: int
    standard_id: int
    standard_code: str
    code: str
    name: str
    description: str | None = None
    status: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExamRevisionOut(MetadataModel):
    id: int
    specification_id: int
    specification_code: str
    code: str
    version: str
    name: str
    description: str | None = None
    status: str
    is_default: bool
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExamLevelOut(MetadataModel):
    id: int
    revision_id: int
    revision_code: str
    code: str
    level_number: int | None = None
    display_name: str
    description: str | None = None
    sort_order: int
    status: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ScoringPolicyOut(MetadataModel):
    id: int
    revision_id: int | None = None
    code: str
    name: str
    version: str
    policy_type: str
    configuration: dict[str, Any] = Field(default_factory=dict)
    status: str


class BlueprintSection(BaseModel):
    type: str = Field(min_length=1, max_length=40)
    title: str | None = Field(default=None, max_length=180)
    question_count: int = Field(ge=1, le=1000)
    duration_minutes: int = Field(ge=1, le=1440)
    allow_previous: bool = True


class ExamBlueprint(BaseModel):
    schema_version: int = Field(default=1, ge=1)
    revision_id: int | None = Field(default=None, ge=1)
    randomized: bool = False
    allow_previous_section: bool = True
    sections: list[BlueprintSection] = Field(min_length=1, max_length=32)


def normalize_blueprint(
    blueprint: dict[str, Any] | None,
    *,
    revision_id: int | None = None,
) -> dict[str, Any]:
    raw = dict(blueprint or {})
    raw.setdefault("schema_version", 1)
    if revision_id is not None:
        raw.setdefault("revision_id", revision_id)
    return ExamBlueprint.model_validate(raw).model_dump(exclude_none=True)


class LearningTargetUpdate(BaseModel):
    exam_revision_id: int = Field(ge=1)
    exam_level_id: int = Field(ge=1)
