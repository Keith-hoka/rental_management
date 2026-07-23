from pydantic import BaseModel


class SearchHit(BaseModel):
    title: str
    subtitle: str | None = None
    link: str


class SearchResults(BaseModel):
    properties: list[SearchHit]
    leases: list[SearchHit]
    maintenance: list[SearchHit]
    documents: list[SearchHit]
