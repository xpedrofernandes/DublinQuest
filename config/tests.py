# Verify readiness responses, allowed hosts and the rendered exploration page.
from unittest.mock import patch

from django.db import OperationalError
from django.test import SimpleTestCase, override_settings
from django.urls import reverse


@override_settings(ALLOWED_HOSTS=["testserver"])
class HealthTests(SimpleTestCase):
    @patch("config.views.connection")
    def test_ready_when_postgis_responds(self, connection):
        response = self.client.get(reverse("health"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
        connection.cursor.return_value.__enter__.return_value.execute.assert_called_once_with(
            "SELECT PostGIS_Version()"
        )

    @patch("config.views.connection")
    def test_database_failure_is_unavailable_without_internal_details(self, connection):
        connection.cursor.side_effect = OperationalError("private connection details")
        with self.assertLogs("config.views", level="ERROR"):
            response = self.client.get(reverse("health"))
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"status": "unavailable"})

    def test_mutation_is_not_allowed(self):
        self.assertEqual(self.client.post(reverse("health")).status_code, 405)

    @override_settings(DEBUG=False, ALLOWED_HOSTS=["localhost"])
    def test_unknown_host_is_rejected(self):
        self.assertEqual(self.client.get(reverse("health")).status_code, 400)


@override_settings(
    ALLOWED_HOSTS=["testserver"],
    STORAGES={"staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}},
)
class ExplorePageTests(SimpleTestCase):
    def test_page_has_accessible_builder_map_and_local_assets(self):
        response = self.client.get(reverse("explore"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Referrer-Policy"], "strict-origin-when-cross-origin")
        self.assertTemplateUsed(response, "explore.html")
        for text in ['lang="en"', 'id="map"', 'id="adventure-form"',
                     'id="saved-section"', 'id="nearby"', 'id="intersections"',
                     'id="park-search-form"', 'aria-live="polite"',
                     '/static/vendor/leaflet/leaflet.js', '/static/js/explore.js',
                     'OpenStreetMap contributors', 'Dublin City Council']:
            self.assertContains(response, text)

    def test_explore_does_not_accept_mutations(self):
        self.assertEqual(self.client.post(reverse("explore")).status_code, 405)
