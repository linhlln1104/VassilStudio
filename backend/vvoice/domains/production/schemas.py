from __future__ import annotations

from typing import Any, Generic, Literal, TypeVar
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ProjectCreate(Input):
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=4000)


class ProjectPatch(Input):
    expected_revision: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=4000)


class SegmentCreate(Input):
    external_id: str | None = Field(default=None, min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=100_000)
    language: str = Field(default="vi", min_length=2, max_length=20)
    voice_id: str | None = Field(default=None, max_length=128)
    model_id: str | None = Field(default=None, max_length=128)
    position: int = Field(default=0, ge=0)


class SegmentPatch(Input):
    expected_revision: int = Field(ge=1)
    text: str | None = Field(default=None, min_length=1, max_length=100_000)
    language: str | None = Field(default=None, min_length=2, max_length=20)
    voice_id: str | None = Field(default=None, max_length=128)
    model_id: str | None = Field(default=None, max_length=128)
    position: int | None = Field(default=None, ge=0)


class TakeCreate(Input):
    expected_revision: int = Field(ge=1)
    voice_id: str | None = Field(default=None, max_length=128)
    model_id: str | None = Field(default=None, max_length=128)
    num_steps: int | None = None
    speed: float | None = Field(default=None, allow_inf_nan=False)


class TakeReview(Input):
    expected_revision: int = Field(ge=1)
    status: Literal["pending", "approved", "rejected"]
    note: str = Field(default="", max_length=4000)


class TakeSelection(Input):
    expected_revision: int = Field(ge=1)
    take_id: str


class DictionaryEntry(Input):
    source: str = Field(min_length=1, max_length=200)
    replacement: str = Field(min_length=1, max_length=500)
    language: Literal["vi", "en"] | None = None


class DictionaryUpdate(Input):
    expected_revision: int = Field(ge=1)
    entries: list[DictionaryEntry] = Field(max_length=1000)


class DictionaryPreview(Input):
    text: str = Field(min_length=1, max_length=100_000)
    language: str = "vi"


class BatchDefaults(Input):
    language: str = "vi"
    voice_id: str | None = None
    model_id: str | None = None
    num_steps: int | None = None
    speed: float | None = Field(default=None, allow_inf_nan=False)


class BatchInput(Input):
    project_id: str
    name: str = Field(default="Batch", min_length=1, max_length=160)
    rows: list[dict] | None = Field(default=None, min_length=1, max_length=10_000)
    csv_text: str | None = Field(default=None, min_length=1, max_length=10_000_000)
    defaults: BatchDefaults = Field(default_factory=BatchDefaults)
    preflight_token: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def one_source(self):
        if (self.rows is None) == (self.csv_text is None):
            raise ValueError("Provide exactly one of rows or csv_text")
        if self.rows is not None and sum(len(str(row)) for row in self.rows) > 10_000_000:
            raise ValueError("Batch JSON input exceeds the 10 MB text limit")
        return self


class RetryFailed(Input):
    item_ids: list[str] | None = Field(default=None, max_length=10_000)


class ProjectMember(Input):
    principal_id: str = Field(min_length=1, max_length=200)
    role: Literal["reader", "editor", "reviewer"]


class MembersUpdate(Input):
    expected_revision: int = Field(ge=1)
    members: list[ProjectMember] = Field(max_length=1000)


class RecordResponse(BaseModel):
    model_config = ConfigDict(extra="allow")


class ProjectResponse(RecordResponse):
    project_id: str
    name: str
    description: str
    owner_id: str
    members: list[ProjectMember]
    revision: int
    created_at: str
    updated_at: str


class SegmentResponse(RecordResponse):
    segment_id: str
    project_id: str
    external_id: str
    text: str
    language: str
    voice_id: str | None
    model_id: str | None
    position: int
    revision: int
    script_revision: int
    selected_take_id: str | None
    created_at: str
    updated_at: str


class TakeResponse(RecordResponse):
    take_id: str
    project_id: str
    segment_id: str
    segment_revision: int
    external_id: str
    text: str
    normalized_text: str
    voice_id: str
    model_id: str
    language: str
    status: Literal["pending", "queued", "running", "cancelling", "succeeded", "failed", "cancelled"]
    review_status: Literal["pending", "approved", "rejected"]
    review_note: str
    reviewed_by: str | None
    reviewed_at: str | None
    job_id: str | None
    revision: int
    audio_url: str | None
    error: str | None
    provenance: dict[str, Any]
    created_at: str
    updated_at: str


class DictionaryResponse(RecordResponse):
    project_id: str
    revision: int
    entries: list[DictionaryEntry]


class BatchResponse(RecordResponse):
    batch_id: str
    project_id: str
    name: str
    status: Literal["running", "cancelling", "succeeded", "completed_with_errors", "cancelled"]
    counts: dict[str, int]
    item_count: int
    cancel_requested: bool
    revision: int
    created_at: str
    updated_at: str


class BatchItemResponse(TakeResponse):
    item_id: str
    batch_id: str
    row_number: int
    take_ids: list[str]


class AnalyzeRow(RecordResponse):
    row_number: int
    external_id: str
    text: str
    normalized_text: str
    errors: list[str]
    warnings: list[str]


class AnalyzeResponse(BaseModel):
    can_submit: bool
    row_count: int
    rows: list[AnalyzeRow]
    errors: list[str]
    dictionary_revision: int
    preflight_token: str


T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
