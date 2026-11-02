import json
import uuid

from django.contrib.auth import get_user_model
from django.contrib.gis.geos import MultiPolygon, Point, Polygon
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.test import override_settings
from rest_framework.test import APIClient, APITestCase

from adventures.models import Adventure, AdventureStop
from places.models import Park, Place


class SpatialAPITests(APITestCase):
    def setUp(self):
        self.origin = Point(-6.26, 53.35, srid=4326)
        self.origin.transform(2157)
        self.x, self.y = self.origin.coords
        self.inside = self.place("Inside", 100, 100)
        self.edge = self.place("Boundary", 500, 200)
        self.at_radius = self.place("At radius", 1000, 0, category="public_art")
        self.outside = self.place("Outside", 1001, 0)
        self.hidden = self.place("Hidden", 5, 5, active=False)
        self.park = self.park_record("Inside park", 0, 0, 500, 500)
        self.touching = self.park_record("Touching circle", 1000, 0, 1020, 20)
        self.corner = self.park_record("Outside circle inside bbox", 800, 800, 900, 900)
        self.staff = get_user_model().objects.create_user("staff", password="test-only-password", is_staff=True)
        self.member = get_user_model().objects.create_user("member", password="test-only-password")
        self.query = {"lat":53.35,"lng":-6.26,"radius_m":1000}

    def place(self, name, dx, dy, **extra):
        return Place.objects.create(name=name, source_key=str(uuid.uuid4()),
            point=Point(self.x+dx,self.y+dy,srid=2157), category=extra.pop("category","heritage"), **extra)

    def park_record(self, name, left, bottom, right, top):
        polygon = Polygon(((self.x+left,self.y+bottom),(self.x+right,self.y+bottom),
            (self.x+right,self.y+top),(self.x+left,self.y+top),(self.x+left,self.y+bottom)),srid=2157)
        return Park.objects.create(name=name, source_key=str(uuid.uuid4()),boundary=MultiPolygon(polygon,srid=2157))

    def ids(self, response):
        self.assertEqual(response.status_code,200,response.data)
        self.assertEqual(response.data["type"],"FeatureCollection")
        self.assertIsInstance(response.data["features"],list)
        return [feature["id"] for feature in response.data["features"]]

    def test_list_detail_categories_filter_and_pagination(self):
        response=self.client.get("/api/places/",{"categories":"public_art","page_size":1})
        self.assertEqual(self.ids(response),[self.at_radius.pk])
        response=self.client.get(f"/api/places/{self.inside.pk}/")
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.data["type"],"Feature")
        coordinate=response.data["geometry"]["coordinates"]
        self.assertTrue(-7 < coordinate[0] < -5)
        self.assertTrue(53 < coordinate[1] < 54)
        self.assertIsNone(response.data["properties"]["source"])
        page=self.client.get("/api/places/",{"page_size":2})
        self.assertEqual(len(self.ids(page)),2)
        self.assertEqual(page.data["count"],4)
        self.assertIsNotNone(page.data["next"])
        self.assertEqual(self.client.get(f"/api/places/{self.hidden.pk}/").status_code,404)
        self.assertEqual(len(self.client.get("/api/categories/").data),4)
        self.assertEqual(self.client.get("/api/places/?format=json").status_code,200)
        self.assertEqual(self.client.get("/api/places/nearby.json",self.query).status_code,200)

    def test_proximity_is_metric_ordered_inclusive_and_filtered(self):
        with CaptureQueriesContext(connection) as queries:
            response=self.client.get("/api/places/nearby/",self.query)
        self.assertEqual(self.ids(response),[self.inside.pk,self.edge.pk,self.at_radius.pk])
        self.assertAlmostEqual(response.data["features"][-1]["properties"]["distance_m"],1000,places=2)
        self.assertTrue(any("ST_DWithin" in q["sql"] for q in queries))
        filtered=self.client.get("/api/places/nearby/",{**self.query,"categories":"public_art"})
        self.assertEqual(self.ids(filtered),[self.at_radius.pk])
        empty=self.client.get("/api/places/nearby/",{"lat":54,"lng":-7,"radius_m":250})
        self.assertEqual(self.ids(empty),[])

    def test_containment_includes_boundary_points_and_excludes_outside(self):
        with CaptureQueriesContext(connection) as queries:
            response=self.client.get(f"/api/parks/{self.park.pk}/places/")
        self.assertEqual(set(self.ids(response)),{self.inside.pk,self.edge.pk})
        self.assertTrue(any("ST_CoveredBy" in q["sql"] for q in queries))
        self.assertEqual(self.client.get("/api/parks/999999/places/").status_code,404)

    def test_intersection_uses_postgis_buffer_not_bounding_box(self):
        with CaptureQueriesContext(connection) as queries:
            response=self.client.get("/api/parks/intersecting/",self.query)
        self.assertEqual(set(self.ids(response)),{self.park.pk,self.touching.pk})
        self.assertNotIn(self.corner.pk,self.ids(response))
        self.assertEqual(response.data["search_area"]["type"],"Polygon")
        self.assertTrue(any("ST_Buffer" in q["sql"] for q in queries))
        self.assertTrue(any("ST_Intersects" in q["sql"] for q in queries))

    def test_invalid_query_inputs_return_400(self):
        for params in [{}, {"lat":91},{"lng":181},{"lat":"nan"},{"lng":"inf"},
                       {"radius_m":-1},{"radius_m":0},{"radius_m":249},{"radius_m":5001},
                       {"radius_m":"abc"},{"categories":"unknown"},{"categories":"heritage,heritage"},
                       {"categories":""},{"page":0},{"page_size":101},{"unexpected":"value"}]:
            data=params if not params else {**self.query,**params}
            with self.subTest(params=params):
                self.assertEqual(self.client.get("/api/places/nearby/",data).status_code,400)
        self.assertEqual(self.client.get("/api/places/?categories=heritage&categories=park").status_code,400)
        self.assertEqual(self.client.get("/api/parks/intersecting/",{**self.query,"categories":"park"}).status_code,400)

    def point_payload(self):
        return {"name":"Temporary test place","category":"heritage",
            "point":{"type":"Point","coordinates":[-6.26,53.35]}}

    def test_anonymous_and_nonstaff_cannot_write(self):
        for user in [None,self.member]:
            self.client.force_authenticate(user=user)
            self.assertEqual(self.client.post("/api/places/",self.point_payload(),format="json").status_code,403)
            self.assertEqual(self.client.patch(f"/api/places/{self.inside.pk}/",{"name":"Changed"},format="json").status_code,403)
            self.assertEqual(self.client.delete(f"/api/places/{self.inside.pk}/").status_code,403)
            self.assertEqual(self.client.post("/api/parks/",{},format="json").status_code,403)

    def test_staff_point_crud_and_geometry_validation(self):
        self.client.force_authenticate(self.staff)
        response=self.client.post("/api/places/",self.point_payload(),format="json")
        self.assertEqual(response.status_code,201,response.data)
        pk=response.data["id"]
        point=Place.objects.get(pk=pk)
        self.assertEqual(point.point.srid,2157)
        self.assertIsNone(point.source_id)
        self.assertTrue(point.source_key.startswith("staff:"))
        patch=self.client.patch(f"/api/places/{pk}/",{"point":{"type":"Point","coordinates":[-6.25,53.35]}},format="json")
        self.assertEqual(patch.status_code,200,patch.data)
        self.assertAlmostEqual(patch.data["geometry"]["coordinates"][0],-6.25,places=6)
        self.assertEqual(self.client.delete(f"/api/places/{pk}/").status_code,204)
        self.assertFalse(Place.objects.filter(pk=pk).exists())
        for geometry in [None,"POINT(-6 53)",{"type":"Point","coordinates":[181,53]},
                         {"type":"Point","coordinates":[-6,53,1]},
                         {"type":"Point","coordinates":[True,53]},
                         {"type":"Point","coordinates":[-6,53],"crs":"EPSG:2157"}]:
            payload={**self.point_payload(),"point":geometry}
            self.assertEqual(self.client.post("/api/places/",payload,format="json").status_code,400)
        self.assertEqual(self.client.post("/api/places/",{**self.point_payload(),"source":1},format="json").status_code,400)
        for invalid_body in [[],[{}],"invalid",123]:
            self.assertEqual(self.client.post("/api/places/",invalid_body,format="json").status_code,400)

    def test_park_crud_keeps_representative_point_synchronized(self):
        self.client.force_authenticate(self.staff)
        boundary=self.park.boundary.clone();boundary.transform(4326)
        payload={"name":"Temporary test park","boundary":json.loads(boundary.geojson)}
        response=self.client.post("/api/parks/",payload,format="json")
        self.assertEqual(response.status_code,201,response.data)
        park=Park.objects.get(pk=response.data["id"])
        self.assertTrue(park.boundary.covers(park.place.point))
        self.assertEqual(self.client.patch(f"/api/places/{park.place.pk}/",{"name":"Bypass"},format="json").status_code,400)
        boundary=self.touching.boundary.clone();boundary.transform(4326)
        response=self.client.patch(f"/api/parks/{park.pk}/",{"name":"Moved park","boundary":json.loads(boundary.geojson),"active":False},format="json")
        self.assertEqual(response.status_code,200,response.data)
        park.refresh_from_db();park.place.refresh_from_db()
        self.assertTrue(park.boundary.covers(park.place.point))
        self.assertEqual(park.place.name,"Moved park")
        self.assertFalse(park.place.active)
        place_pk=park.place.pk
        self.assertEqual(self.client.delete(f"/api/parks/{park.pk}/").status_code,204)
        self.assertFalse(Place.objects.filter(pk=place_pk).exists())
        invalid={"name":"Invalid park","boundary":{"type":"MultiPolygon","coordinates":[[[[-6.26,53.35],[-6.25,53.36],[-6.26,53.36],[-6.25,53.35],[-6.26,53.35]]]]}}
        self.assertEqual(self.client.post("/api/parks/",invalid,format="json").status_code,400)

    def test_used_place_cannot_be_deleted(self):
        adventure=Adventure.objects.create(owner_uuid=uuid.uuid4(),title="Test",start=self.origin,categories=["heritage"])
        AdventureStop.objects.create(adventure=adventure,place=self.inside,position=1,distance_from_start_m=1,distance_from_previous_m=1)
        self.client.force_authenticate(self.staff)
        self.assertEqual(self.client.delete(f"/api/places/{self.inside.pk}/").status_code,409)
        self.assertTrue(Place.objects.filter(pk=self.inside.pk).exists())

    @override_settings(STORAGES={"staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}, "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"}})
    def test_session_authenticated_write_requires_csrf(self):
        client=APIClient(enforce_csrf_checks=True)
        self.assertTrue(client.login(username="staff",password="test-only-password"))
        self.assertEqual(client.post("/api/places/",self.point_payload(),format="json").status_code,403)
        self.assertEqual(client.get("/api-auth/login/").status_code,200)
        token=client.cookies["csrftoken"].value
        response=client.post("/api/places/",self.point_payload(),format="json",HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code,201,response.data)

    def test_openapi_pagination_documents_features_array(self):
        from drf_spectacular.generators import SchemaGenerator
        schema = SchemaGenerator().get_schema(public=True)
        for path in ("/api/places/", "/api/parks/", "/api/places/nearby/", "/api/parks/{id}/places/"):
            ref = schema["paths"][path]["get"]["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
            page = schema["components"]["schemas"][ref.split("/")[-1]]
            self.assertNotIn("results", page["properties"])
            self.assertEqual(page["properties"]["features"]["type"], "array")
            feature_ref = page["properties"]["features"]["items"]["$ref"]
            feature = schema["components"]["schemas"][feature_ref.split("/")[-1]]
            self.assertIn("geometry", feature["properties"])
