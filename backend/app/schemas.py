"""Pydantic 契约：LLM 输出与请求结构。"""

import re
from datetime import date as date_type
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ListText = Annotated[str, Field(max_length=2_000)]


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Item(ContractModel):
    date: str = Field(default="", max_length=10, pattern=r"^(?:|\d{4}-\d{2}-\d{2})$")
    summary: str = Field(default="", max_length=300)
    detail: str = Field(default="", max_length=4_000)
    result: str = Field(default="", max_length=2_000)
    next_step: str = Field(default="", max_length=2_000)

    @field_validator("date")
    @classmethod
    def validate_calendar_date(cls, value: str) -> str:
        if value:
            date_type.fromisoformat(value)
        return value


class Section(ContractModel):
    category: Literal["工作", "学习", "比赛", "活动", "其他"] = "其他"
    items: list[Item] = Field(default_factory=list, max_length=100)


class Report(ContractModel):
    title: str = Field(default="", max_length=300)
    sections: list[Section] = Field(default_factory=list, max_length=20)


class Topic(ContractModel):
    topic: str = Field(default="", max_length=300)
    related_items: list[ListText] = Field(default_factory=list, max_length=100)
    explanation: str = Field(default="", max_length=4_000)
    key_points: list[ListText] = Field(default_factory=list, max_length=100)
    references: list[ListText] = Field(default_factory=list, max_length=100)


class TechSummary(ContractModel):
    title: str = Field(default="", max_length=300)
    topics: list[Topic] = Field(default_factory=list, max_length=100)


class Organized(ContractModel):
    report: Report
    tech_summary: TechSummary

    @model_validator(mode="after")
    def require_report_content(self):
        if not any(section.items for section in self.report.sections):
            raise ValueError("工作汇报至少需要包含一条事项")
        return self


class OrganizeRequest(ContractModel):
    raw_input: str = Field(min_length=1, max_length=40_000)


class ChatRequest(ContractModel):
    session_id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9._:-]+$")
    message: str = Field(default="", max_length=8_000)
    attachment_ids: list[str] = Field(default_factory=list, max_length=12)
    mode: Literal["normal", "advanced"] = "advanced"
    template_id: int | None = Field(default=None, gt=0)


class SettingsRequest(ContractModel):
    week_one_start: str = Field(min_length=10, max_length=10)
    purpose_mode: str = Field(default="default", max_length=20)
    custom_purpose_name: str = Field(default="", max_length=30)
    custom_purpose_description: str = Field(default="", max_length=500)
    detail_level: str = Field(default="standard", max_length=20)
    tone: str = Field(default="natural", max_length=20)


TemplateBlockType = Literal["paragraph", "field", "bullet_list", "numbered_list", "table"]


class TemplateColumn(ContractModel):
    id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    label: str = Field(min_length=1, max_length=100)
    instruction: str = Field(default="", max_length=500)


class TemplateBlock(ContractModel):
    id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    type: TemplateBlockType
    label: str = Field(min_length=1, max_length=100)
    instruction: str = Field(default="", max_length=500)
    required: bool = False
    columns: list[TemplateColumn] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def validate_columns(self):
        if self.type == "table" and not self.columns:
            raise ValueError("表格至少需要一列")
        if self.type != "table" and self.columns:
            raise ValueError("只有表格内容块可以包含列")
        column_ids = [column.id for column in self.columns]
        if len(column_ids) != len(set(column_ids)):
            raise ValueError("表格列 ID 不能重复")
        return self


class TemplateSection(ContractModel):
    id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    title: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)
    blocks: list[TemplateBlock] = Field(min_length=1, max_length=100)


class TemplateDefinition(ContractModel):
    version: Literal[1] = 1
    title_pattern: str = Field(min_length=1, max_length=200)
    sections: list[TemplateSection] = Field(min_length=1, max_length=20)

    @field_validator("title_pattern")
    @classmethod
    def validate_title_variables(cls, value: str) -> str:
        allowed = {"week_number", "date_range", "week_start", "week_end"}
        variables = set(re.findall(r"\{([A-Za-z0-9_]+)\}", value))
        if variables - allowed:
            raise ValueError("标题包含不支持的变量")
        return value

    @model_validator(mode="after")
    def validate_unique_ids(self):
        section_ids = [section.id for section in self.sections]
        if len(section_ids) != len(set(section_ids)):
            raise ValueError("章节 ID 不能重复")
        block_ids = [block.id for section in self.sections for block in section.blocks]
        if len(block_ids) != len(set(block_ids)):
            raise ValueError("内容块 ID 不能重复")
        if len(block_ids) > 100:
            raise ValueError("模板最多包含 100 个内容块")
        return self


class CustomBlockValue(ContractModel):
    id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    type: TemplateBlockType
    text: str = Field(default="", max_length=8_000)
    items: list[ListText] = Field(default_factory=list, max_length=100)
    rows: list[dict[str, str]] = Field(default_factory=list, max_length=200)

    @model_validator(mode="after")
    def validate_value_shape(self):
        if self.type in {"paragraph", "field"} and (self.items or self.rows):
            raise ValueError("段落或字段只能使用 text")
        if self.type in {"bullet_list", "numbered_list"} and (self.text or self.rows):
            raise ValueError("列表只能使用 items")
        if self.type == "table" and (self.text or self.items):
            raise ValueError("表格只能使用 rows")
        for row in self.rows:
            if len(row) > 20:
                raise ValueError("表格单行列数过多")
            if any(len(str(value)) > 2_000 for value in row.values()):
                raise ValueError("表格单元格内容过长")
        return self


class CustomSectionValue(ContractModel):
    id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    title: str = Field(min_length=1, max_length=100)
    blocks: list[CustomBlockValue] = Field(default_factory=list, max_length=100)


class CustomDocument(ContractModel):
    title: str = Field(min_length=1, max_length=300)
    sections: list[CustomSectionValue] = Field(min_length=1, max_length=20)


class TemplateDraftCreateRequest(ContractModel):
    source_type: Literal["manual"] = "manual"


class TemplateDraftUpdateRequest(ContractModel):
    definition: TemplateDefinition
    base_revision: int | None = Field(default=None, ge=0)


class TemplateAnalyzeRequest(ContractModel):
    session_id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9._:-]+$")
    attachment_ids: list[str] = Field(min_length=1, max_length=5)


class TemplateDraftChatRequest(ContractModel):
    message: str = Field(min_length=1, max_length=4_000)
    base_revision: int | None = Field(default=None, ge=0)


class TemplateSaveRequest(ContractModel):
    draft_id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9._:-]+$")
    draft_revision: int = Field(ge=0)
    name: str = Field(min_length=1, max_length=30)


class TemplateRenameRequest(ContractModel):
    name: str = Field(min_length=1, max_length=30)


class TemplateSelectionRequest(ContractModel):
    template_id: int | None = Field(default=None, gt=0)
