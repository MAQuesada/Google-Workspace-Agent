from pydantic import BaseModel, Field


class DateExtractionResult(BaseModel):
    reasoning: str = Field(
        ..., description="Step-by-step reasoning process to give the correct answer"
    )
    start_datetime: str = Field(..., description="Start date in ISO 8601 format.")
    end_datetime: str = Field(..., description="End date in ISO 8601 format.")
    description: str = Field(
        default="",
        description="Message explaining errors or ambiguities (only for errors).",
    )
