# Mock the routing provider to test geometry validation, security and safe fallback.
"""Routing tests never contact the external provider."""
import copy
import io
import json
import urllib.error
from unittest.mock import patch

from django.contrib.gis.geos import LineString, Point
from django.test import SimpleTestCase, override_settings
from rest_framework.test import APIClient, APITestCase

from adventures.models import Adventure
from adventures.routing import walking_route
from places.models import Place

FAKE_KEY = "test-routing-key-not-a-real-credential"
COORDINATES = [[-6.26, 53.35], [-6.259, 53.35], [-6.258, 53.35]]


def provider_data():
    return {"type": "FeatureCollection", "features": [{"type": "Feature",
        "geometry": {"type": "LineString", "coordinates": copy.deepcopy(COORDINATES)},
        "properties": {"summary": {"distance": 150.0, "duration": 110.0}, "way_points": [0, 1, 2]}}]}


@override_settings(ORS_API_KEY=FAKE_KEY)
class RoutingHelperTests(SimpleTestCase):
    def setUp(self):
        self.path = LineString(COORDINATES, srid=4326).transform(2157, clone=True)

    def invoke(self, data):
        with patch("adventures.routing.urllib.request.build_opener") as opener:
            opener.return_value.open.return_value.__enter__.return_value.read.return_value = json.dumps(data).encode()
            result = walking_route(self.path)
            return result, opener

    def test_success_preserves_order_coordinates_and_server_only_key(self):
        original = self.path.ewkt
        result, opener = self.invoke(provider_data())
        self.assertEqual(result["status"], "available")
        self.assertEqual(result["route"]["coordinates"], COORDINATES)
        self.assertEqual(result["way_points"], [0, 1, 2])
        self.assertEqual(result["distance_m"], 150)
        self.assertEqual(result["duration_s"], 110)
        self.assertTrue(all(w["displacement_m"] < .01 for w in result["waypoints"]))
        request = opener.return_value.open.call_args.args[0]
        self.assertEqual(request.headers["Authorization"], FAKE_KEY)
        self.assertEqual(request.full_url, "https://api.heigit.org/openrouteservice/v2/directions/foot-walking/geojson")
        payload = json.loads(request.data)
        self.assertEqual(payload["radiuses"], [50, 50, 50])
        self.assertFalse(payload["instructions"])
        self.assertEqual(opener.return_value.open.call_args.kwargs["timeout"], 10)
        self.assertNotIn(FAKE_KEY, json.dumps(result))
        self.assertEqual(self.path.ewkt, original)
        self.assertEqual(self.path.srid, 2157)

    def test_waypoint_indices_preserve_intermediate_route_vertices(self):
        data = provider_data()
        geometry = data['features'][0]['geometry']
        geometry['coordinates'].insert(1, [-6.2595, 53.3501])
        data['features'][0]['properties']['way_points'] = [0, 2, 3]
        result, _ = self.invoke(data)
        self.assertEqual(result['status'], 'available')
        self.assertEqual(result['way_points'], [0, 2, 3])
        self.assertEqual(result['route']['coordinates'], geometry['coordinates'])

    @override_settings(ORS_API_KEY="")
    def test_missing_key_never_contacts_provider(self):
        with patch("adventures.routing.urllib.request.build_opener") as opener:
            self.assertEqual(walking_route(self.path)["status"], "unavailable")
            opener.assert_not_called()

    def test_timeout_and_provider_errors_are_sanitized_without_retries(self):
        errors = [TimeoutError(FAKE_KEY), urllib.error.URLError(FAKE_KEY)]
        errors += [urllib.error.HTTPError("https://provider.invalid", code, FAKE_KEY, {}, io.BytesIO(FAKE_KEY.encode())) for code in (400, 401, 403, 429, 500, 302)]
        for error in errors:
            with self.subTest(error=type(error).__name__), patch("adventures.routing.urllib.request.build_opener") as opener:
                opener.return_value.open.side_effect = error
                result = walking_route(self.path)
                self.assertEqual(result["status"], "unavailable")
                self.assertNotIn(FAKE_KEY, json.dumps(result))
                self.assertEqual(opener.return_value.open.call_count, 1)

    def test_malformed_geometry_summary_waypoints_and_excess_snapping_fall_back(self):
        invalid = [{}, {"type": "FeatureCollection", "features": []}]
        for key, value in [("geometry", {"type": "Point", "coordinates": [0, 0]}),
                ("geometry", {"type": "LineString", "coordinates": [[-6.26, 53.35], [True, 53.35]]})]:
            data = provider_data(); data["features"][0][key] = value; invalid.append(data)
        for key, value in [("summary", {"distance": float("nan"), "duration": 100}),
                ("summary", {"distance": 100, "duration": -1}),
                ("way_points", [0, 2]), ("way_points", [0, 2, 1]), ("way_points", [0, True, 2])]:
            data = provider_data(); data["features"][0]["properties"][key] = value; invalid.append(data)
        data = provider_data(); data["features"][0]["geometry"]["coordinates"][1] = [-6.25, 53.35]; invalid.append(data)
        for data in invalid:
            with self.subTest(data=data):
                result, _ = self.invoke(data)
                self.assertEqual(result["status"], "unavailable")
        for raw in (b"<html>provider error</html>", b"x" * 2_000_001, FAKE_KEY.encode()):
            with patch("adventures.routing.urllib.request.build_opener") as opener:
                opener.return_value.open.return_value.__enter__.return_value.read.return_value = raw
                self.assertEqual(walking_route(self.path)["status"], "unavailable")

    def test_warning_is_not_relayed_as_provider_text(self):
        data = provider_data()
        data["features"][0]["properties"]["warnings"] = [{"message": "untrusted provider text"}]
        result, _ = self.invoke(data)
        self.assertEqual(result["status"], "available")
        self.assertTrue(result["warnings"])
        self.assertNotIn("untrusted provider text", json.dumps(result))


@override_settings(ORS_API_KEY="")
class WalkingRouteAPITests(APITestCase):
    def setUp(self):
        self.client = APIClient(enforce_csrf_checks=True)
        self.token = self.client.get("/api/session/").data["csrfToken"]
        for index, coordinates in enumerate(COORDINATES[1:]):
            Place.objects.create(name=f"Routing fixture {index}", category="heritage", source_key=f"routing:{index}", point=Point(*coordinates, srid=4326).transform(2157, clone=True))
        response = self.client.post("/api/adventures/", {"lat":53.35,"lng":-6.26,"categories":["heritage"],"stop_count":2}, format="json", HTTP_X_CSRFTOKEN=self.token)
        self.assertEqual(response.status_code,201)
        self.adventure = Adventure.objects.get(pk=response.data["id"])
        self.url = f"/api/adventures/{self.adventure.pk}/walking-route/"

    def post(self, **kwargs):
        return self.client.post(self.url, {}, format="json", HTTP_X_CSRFTOKEN=self.token, **kwargs)

    def test_missing_key_is_usable_fallback_without_changing_database(self):
        path, updated = self.adventure.path.ewkt, self.adventure.updated_at
        response = self.post()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "unavailable")
        self.assertIn("not configured", response.data["detail"])
        self.assertIn("no-store", response["Cache-Control"])
        self.adventure.refresh_from_db()
        self.assertEqual(self.adventure.path.ewkt, path)
        self.assertEqual(self.adventure.updated_at, updated)
        self.assertEqual(self.adventure.stops.count(), 2)

    @patch("adventures.views.walking_route")
    def test_owner_csrf_unknown_body_and_get_rejected_before_provider(self, provider):
        self.assertEqual(self.client.post(self.url, {}, format="json").status_code, 403)
        self.assertEqual(self.post(HTTP_ORIGIN="https://foreign.invalid").status_code, 403)
        other = APIClient(enforce_csrf_checks=True)
        token = other.get("/api/session/").data["csrfToken"]
        self.assertEqual(other.post(self.url, {}, format="json", HTTP_X_CSRFTOKEN=token).status_code, 404)
        self.assertEqual(self.client.post(self.url, {"coordinates":COORDINATES}, format="json",HTTP_X_CSRFTOKEN=self.token).status_code,400)
        self.assertEqual(self.client.get(self.url).status_code,405)
        provider.assert_not_called()

    @patch("adventures.views.walking_route")
    def test_success_and_cooldown_only_one_provider_call(self, provider):
        provider.return_value = {"status":"available","route":provider_data()["features"][0]["geometry"],"distance_m":150,"duration_s":110}
        response = self.post()
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.data["status"],"available")
        self.assertEqual(provider.call_args.args[0].ewkt,self.adventure.path.ewkt)
        second = self.post()
        self.assertEqual(second.data["status"],"unavailable")
        self.assertIn("30 seconds",second.data["detail"])
        provider.assert_called_once()

    @patch("adventures.views.walking_route")
    def test_moved_attraction_requires_regeneration(self, provider):
        place = self.adventure.stops.first().place
        place.point = Point(place.point.x + 100, place.point.y, srid=2157)
        place.save()
        self.assertIn("regenerate",self.post().data["detail"])
        provider.assert_not_called()
