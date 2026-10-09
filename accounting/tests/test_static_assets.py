from pathlib import Path

from django.conf import settings
from django.test import RequestFactory, SimpleTestCase, override_settings

from accounting.context_processors import static_asset_versions


class StaticAssetVersionTests(SimpleTestCase):
    def setUp(self):
        self.request = RequestFactory().get("/")

    @override_settings(DEBUG=True)
    def test_development_version_matches_dashboard_stylesheet_mtime(self):
        context = static_asset_versions(self.request)
        stylesheet = Path(settings.BASE_DIR) / "static" / "accounting" / "dashboard.css"

        self.assertEqual(
            context["dashboard_css_version"],
            str(stylesheet.stat().st_mtime_ns),
        )

    @override_settings(DEBUG=False)
    def test_production_does_not_add_a_query_version(self):
        self.assertEqual(
            static_asset_versions(self.request),
            {"dashboard_css_version": ""},
        )

    def test_shared_stylesheet_has_the_compact_operational_ui_contract(self):
        stylesheet = Path(settings.BASE_DIR) / "static" / "accounting" / "dashboard.css"
        css = stylesheet.read_text(encoding="utf-8")

        self.assertIn("Operational UI refinement", css)
        self.assertIn(".workday-header", css)
        self.assertIn(".priority-row", css)
        self.assertIn(".topbar h1 { font-size: 1.7rem", css)
        self.assertNotIn("font-size: clamp(2.3rem, 4.6vw, 5.3rem)", css[css.index("Operational UI refinement"):])
