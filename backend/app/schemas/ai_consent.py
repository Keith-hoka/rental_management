from pydantic import BaseModel


class AiConsentToggle(BaseModel):
    enabled: bool


class AiConsentState(BaseModel):
    features: dict[str, bool]
    disclosure_version: str
