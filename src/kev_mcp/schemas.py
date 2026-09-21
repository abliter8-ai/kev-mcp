"""Bounded tool inputs using Kev's native question vocabulary."""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator


class QuestionBase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    instructions: str = Field(min_length=1, max_length=32000)


class Noul(QuestionBase):
    type: Literal["noul"]
    criteria: dict[str, str | None] | None = None

    @model_validator(mode="after")
    def check_criteria(self):
        if self.criteria and set(self.criteria) - {"true", "false"}:
            raise ValueError("noul criteria keys must be true or false")
        return self


class Choice(QuestionBase):
    type: Literal["choice"]
    criteria: dict[str, str | None] = Field(min_length=1, max_length=255)


class Score(QuestionBase):
    type: Literal["score"]
    criteria: list[str] = Field(min_length=2, max_length=255)


Question = Annotated[Noul | Choice | Score, Field(discriminator="type")]
Questions = Annotated[dict[str, Question], Field(min_length=1, max_length=16)]
_questions = TypeAdapter(Questions)


def validate_questions(value: Any) -> dict[str, Any]:
    parsed = _questions.validate_python(value)
    return {key: question.model_dump(exclude_none=True) for key, question in parsed.items()}
