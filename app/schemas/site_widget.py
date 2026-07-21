from pydantic import BaseModel


class SiteWidgetUpdate(BaseModel):
    """Admin payload: an on/off flag plus the pasted embed snippet."""

    enabled: bool
    snippet: str = ""


class SiteWidgetOut(BaseModel):
    """Admin view of the site's own support widget config."""

    enabled: bool
    public_key: str
    src: str
    snippet: str


class SiteWidgetPublic(BaseModel):
    """Unauthenticated view the marketing site reads to inject the widget."""

    enabled: bool
    src: str
    public_key: str
