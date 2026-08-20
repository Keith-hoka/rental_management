from datetime import date

from pydantic import BaseModel


class RentSuggestionRequest(BaseModel):
    renewal_start: date
