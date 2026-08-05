"""Map free-text property state to a compliance jurisdiction."""

from typing import Literal

SUPPORTED_JURISDICTIONS = {"NSW", "VIC"}

_ALIASES = {
    "nsw": "NSW",
    "newsouthwales": "NSW",
    "vic": "VIC",
    "victoria": "VIC",
    "qld": "QLD",
    "queensland": "QLD",
    "sa": "SA",
    "southaustralia": "SA",
    "wa": "WA",
    "westernaustralia": "WA",
    "tas": "TAS",
    "tasmania": "TAS",
    "act": "ACT",
    "australiancapitalterritory": "ACT",
    "nt": "NT",
    "northernterritory": "NT",
}

Reason = Literal["ok", "missing", "unsupported"]


class JurisdictionUnresolved(Exception):
    """The property's state does not resolve to a supported jurisdiction."""

    def __init__(self, reason: Reason) -> None:
        super().__init__(reason)
        self.reason: Reason = reason


def normalize_state(text: str | None) -> str | None:
    """The state/territory code for free text, or None when unrecognisable."""
    if text is None:
        return None
    key = "".join(ch for ch in text.lower() if ch.isalpha())
    return _ALIASES.get(key)


def jurisdiction_for(property_state: str | None) -> tuple[str | None, Reason]:
    """Resolve a state value to (supported code, "ok"), or (None, why not)."""
    code = normalize_state(property_state)
    if code is None:
        return (None, "missing")
    if code not in SUPPORTED_JURISDICTIONS:
        return (None, "unsupported")
    return (code, "ok")
