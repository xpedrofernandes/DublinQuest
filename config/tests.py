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
