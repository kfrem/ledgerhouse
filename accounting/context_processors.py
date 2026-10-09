"""Small, non-secret template context values shared by LedgerHouse screens."""

from pathlib import Path

from django.conf import settings


def static_asset_versions(request):
    """Invalidate locally cached dashboard CSS after an edit in development.

    Production uses WhiteNoise's manifest-hashed static filenames, so no query
    string is needed there. The value is based on the source asset's modified
    time and contains no user or environment data.
    """
    if not settings.DEBUG:
        return {"dashboard_css_version": ""}

    stylesheet = Path(settings.BASE_DIR) / "static" / "accounting" / "dashboard.css"
    try:
        version = str(stylesheet.stat().st_mtime_ns)
    except OSError:
        version = ""
    return {"dashboard_css_version": version}
