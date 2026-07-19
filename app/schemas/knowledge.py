from pydantic import BaseModel, model_validator


class KnowledgeCreate(BaseModel):
    source_type: str  # "url" | "text"
    location: str | None = None  # required when source_type == "url"
    title: str | None = None
    text: str | None = None  # required when source_type == "text"

    @model_validator(mode="after")
    def _check(self) -> "KnowledgeCreate":
        if self.source_type == "url" and not self.location:
            raise ValueError("location is required for a url source")
        if self.source_type == "text" and not (self.text and self.text.strip()):
            raise ValueError("text is required for a text source")
        if self.source_type not in ("url", "text"):
            raise ValueError("source_type must be 'url' or 'text'")
        return self


class KnowledgeOut(BaseModel):
    id: int
    organization_id: int
    bot_id: int
    source_type: str
    title: str | None = None
    location: str | None = None
    status: str
    chunk_count: int = 0
    has_file: bool = False          # a downloadable original is stored
    file_size: int | None = None

    class Config:
        from_attributes = True
