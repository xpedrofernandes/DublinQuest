# Exercise quest generation, ownership, CSRF and persistence in an isolated test database.
import io
import uuid

from django.contrib.auth import get_user_model
from django.contrib.gis.geos import MultiPolygon, Point
from django.core.management import call_command
from django.db import connection
from unittest.mock import patch
from rest_framework.test import APIClient, APITestCase

from adventures.generation import generate_adventure
from adventures.models import Adventure, AdventureStop
from places.models import DatasetSource, Park, Place


class AdventureAPITests(APITestCase):
    def setUp(self):
        # Enforce CSRF in tests so anonymous guest writes exercise real protection.
        self.client = APIClient(enforce_csrf_checks=True)
        self.token = self.bootstrap(self.client)
        self.origin = Point(-6.26, 53.35, srid=4326)
        self.origin.transform(2157)
        self.places = []
        for index, (dx, dy, category) in enumerate([(100,0,"heritage"),(200,0,"heritage"),(400,0,"public_art"),(500,100,"street_art"),(600,0,"heritage"),(700,0,"public_art")]):
            self.places.append(Place.objects.create(name=f"Synthetic {index}", source_key=str(index), category=category,
                point=Point(self.origin.x+dx,self.origin.y+dy,srid=2157)))
        self.payload = {"lat":53.35,"lng":-6.26,"categories":["heritage","public_art","street_art"]}

    def bootstrap(self, client):
        response = client.get("/api/session/")
        self.assertEqual(response.status_code,200,response.data)
        self.assertIn("no-store",response["Cache-Control"])
        self.assertIn("csrftoken",client.cookies)
        self.assertIn("sessionid",client.cookies)
        return response.data["csrfToken"]

    def create(self, client=None, token=None, payload=None):
        response=(client or self.client).post("/api/adventures/", self.payload if payload is None else payload,
            format="json",HTTP_X_CSRFTOKEN=token or self.token)
        self.assertEqual(response.status_code,201,response.data)
        return response

    def test_generation_defaults_variety_determinism_and_line_geometry(self):
        first=self.create().data
        second=self.create(payload={**self.payload,"categories":list(reversed(self.payload["categories"]))}).data
        ids=[stop["place"]["id"] for stop in first["stops"]]
        self.assertEqual(ids,[stop["place"]["id"] for stop in second["stops"]])
        self.assertEqual(ids,[self.places[index].pk for index in (0,1,2,3,4)])
        self.assertEqual(len(ids),5)
        self.assertEqual(len(set(ids)),5)
        self.assertEqual({stop["place"]["properties"]["category"] for stop in first["stops"]},set(self.payload["categories"]))
        self.assertEqual((first["radius_m"],first["requested_stops"]),(2000,5))
        self.assertEqual(first["progress"],{"visited":0,"total":5,"percent":0.0,"complete":False})
        self.assertEqual(first["path"]["type"],"LineString")
        self.assertEqual(len(first["path"]["coordinates"]),6)
        self.assertAlmostEqual(first["path"]["coordinates"][0][0],-6.26,places=6)
        self.assertAlmostEqual(first["path"]["coordinates"][0][1],53.35,places=6)
        self.assertEqual([stop["position"] for stop in first["stops"]],list(range(1,6)))
        stored=Adventure.objects.get(pk=first["id"])
        self.assertEqual((stored.start.srid,stored.path.srid,stored.search_area.srid),(2157,2157,2157))
        for stop,coordinates in zip(first["stops"],first["path"]["coordinates"][1:]):
            self.assertEqual(stop["place"]["geometry"]["coordinates"],coordinates)
        self.assertIn("not pedestrian",first["sequence_notice"])
        self.assertNotIn("owner_uuid",first)

    def test_algorithm_excludes_origin_coincident_and_duplicate_coordinates(self):
        Place.objects.create(name="At origin",source_key="origin",category="heritage",point=self.origin)
        Place.objects.create(name="Duplicate coordinates",source_key="duplicate",category="heritage",point=self.places[0].point)
        response=self.create(payload={**self.payload,"stop_count":10})
        self.assertEqual(len(response.data["stops"]),6)
        coordinates=[tuple(stop["place"]["geometry"]["coordinates"]) for stop in response.data["stops"]]
        self.assertEqual(len(coordinates),len(set(coordinates)))
        self.assertTrue(response.data["warnings"])

    def test_one_stop_and_no_locations(self):
        response=self.create(payload={**self.payload,"stop_count":1})
        self.assertEqual(len(response.data["stops"]),1)
        self.assertEqual(len(response.data["path"]["coordinates"]),2)
        before=Adventure.objects.count()
        empty=self.client.post("/api/adventures/",{**self.payload,"lat":54,"lng":-7,"radius_m":250},format="json",HTTP_X_CSRFTOKEN=self.token)
        self.assertEqual(empty.status_code,400)
        self.assertEqual(Adventure.objects.count(),before)

    def test_inactive_places_and_category_filters(self):
        self.places[0].active=False;self.places[0].save()
        active=self.create(payload={**self.payload,"stop_count":10})
        self.assertNotIn(self.places[0].pk,[stop["place"]["id"] for stop in active.data["stops"]])
        park=Park.objects.create(name="Inactive synthetic park",source_key="park",active=False,boundary=MultiPolygon(self.origin.buffer(200),srid=2157))
        Place.objects.create(name="Inactive park representative",source_key="rep",category="park",park=park,point=park.boundary.point_on_surface)
        empty=self.client.post("/api/adventures/",{**self.payload,"categories":["park"]},format="json",HTTP_X_CSRFTOKEN=self.token)
        self.assertEqual(empty.status_code,400)
        response=self.create(payload={**self.payload,"categories":["public_art"],"stop_count":5})
        self.assertEqual(len(response.data["stops"]),2)
        self.assertTrue(response.data["warnings"])
        self.assertTrue(all(stop["place"]["properties"]["category"]=="public_art" for stop in response.data["stops"]))

    def test_anonymous_mutations_require_csrf_including_regeneration_and_delete(self):
        before=Adventure.objects.count()
        self.assertEqual(self.client.post("/api/adventures/",self.payload,format="json").status_code,403)
        self.assertEqual(self.client.post("/api/adventures/",self.payload,format="json",HTTP_X_CSRFTOKEN="invalid").status_code,403)
        self.assertEqual(Adventure.objects.count(),before)
        response=self.create();url=f"/api/adventures/{response.data['id']}/"
        stop_id=response.data["stops"][0]["id"]
        for method,path,data in [("patch",url,{"title":"Changed"}),("post",url+"regenerate/",{}),("patch",url+f"stops/{stop_id}/",{"visited":True}),("delete",url,None)]:
            response=getattr(self.client,method)(path,data,format="json")
            self.assertEqual(response.status_code,403)
        foreign_origin=self.client.post("/api/adventures/",self.payload,format="json",HTTP_X_CSRFTOKEN=self.token,HTTP_ORIGIN="https://other.example")
        self.assertEqual(foreign_origin.status_code,403)

    def test_guest_ownership_is_enforced_for_every_operation_even_for_staff(self):
        first=self.create().data;url=f"/api/adventures/{first['id']}/"
        other=APIClient(enforce_csrf_checks=True);other_token=self.bootstrap(other)
        self.assertEqual(other.get("/api/adventures/").data["count"],0)
        self.assertEqual(other.get(url).status_code,404)
        for method,path,data in [("patch",url,{"title":"Stolen"}),("post",url+"regenerate/",{}),("patch",url+f"stops/{first['stops'][0]['id']}/",{"visited":True}),("delete",url,None)]:
            self.assertEqual(getattr(other,method)(path,data,format="json",HTTP_X_CSRFTOKEN=other_token).status_code,404)
        staff=get_user_model().objects.create_user("staff-guest",is_staff=True)
        other.force_login(staff)
        self.assertEqual(other.get(url).status_code,404)
        forged=self.client.post("/api/adventures/",{**self.payload,"owner_uuid":str(uuid.uuid4())},format="json",HTTP_X_CSRFTOKEN=self.token)
        self.assertEqual(forged.status_code,400)

    def test_persistence_across_requests_progress_rename_and_completion(self):
        response=self.create().data;url=f"/api/adventures/{response['id']}/"
        reconnect=APIClient(enforce_csrf_checks=True);reconnect.cookies=self.client.cookies
        self.assertEqual(reconnect.get(url).status_code,200)
        self.assertEqual(reconnect.get("/api/adventures/").data["count"],1)
        self.assertIn("no-store",reconnect.get(url)["Cache-Control"])
        stop_url=url+f"stops/{response['stops'][0]['id']}/"
        visited=reconnect.patch(stop_url,{"visited":True},format="json",HTTP_X_CSRFTOKEN=self.token)
        self.assertEqual(visited.status_code,200,visited.data)
        self.assertEqual(visited.data["progress"]["visited"],1)
        timestamp=visited.data["stops"][0]["visited_at"]
        repeat=reconnect.patch(stop_url,{"visited":True},format="json",HTTP_X_CSRFTOKEN=self.token)
        self.assertEqual(repeat.data["stops"][0]["visited_at"],timestamp)
        renamed=reconnect.patch(url,{"title":"My adventure"},format="json",HTTP_X_CSRFTOKEN=self.token)
        self.assertEqual(renamed.data["title"],"My adventure")
        self.assertEqual(renamed.data["progress"]["visited"],1)
        for stop in response["stops"]:
            completed=reconnect.patch(url+f"stops/{stop['id']}/",{"visited":True},format="json",HTTP_X_CSRFTOKEN=self.token)
        self.assertTrue(completed.data["progress"]["complete"])
        self.assertEqual(completed.data["progress"]["percent"],100.0)
        unvisited=reconnect.patch(stop_url,{"visited":False},format="json",HTTP_X_CSRFTOKEN=self.token)
        self.assertFalse(unvisited.data["progress"]["complete"])
        self.assertEqual(unvisited.data["progress"]["visited"],4)

    def test_regeneration_resets_stops_after_confirmation_and_preserves_owner(self):
        data=self.create().data;url=f"/api/adventures/{data['id']}/"
        original=Adventure.objects.get(pk=data["id"]);owner=original.owner_uuid;old_path=bytes(original.path.ewkb)
        old_stop=data["stops"][0]["id"]
        self.client.patch(url+f"stops/{old_stop}/",{"visited":True},format="json",HTTP_X_CSRFTOKEN=self.token)
        denied=self.client.post(url+"regenerate/",{"stop_count":2},format="json",HTTP_X_CSRFTOKEN=self.token)
        self.assertEqual(denied.status_code,400)
        self.assertEqual(AdventureStop.objects.filter(adventure=original).count(),5)
        regenerated=self.client.post(url+"regenerate/",{"stop_count":2,"categories":["public_art"],"confirm_reset":True},format="json",HTTP_X_CSRFTOKEN=self.token)
        self.assertEqual(regenerated.status_code,200,regenerated.data)
        original.refresh_from_db()
        self.assertEqual(original.owner_uuid,owner)
        self.assertNotEqual(bytes(original.path.ewkb),old_path)
        self.assertEqual(original.path.num_points,3)
        self.assertEqual(regenerated.data["progress"]["visited"],0)
        self.assertFalse(AdventureStop.objects.filter(pk=old_stop).exists())
        self.assertEqual(self.client.patch(url+f"stops/{old_stop}/",{"visited":True},format="json",HTTP_X_CSRFTOKEN=self.token).status_code,404)
        before=bytes(original.path.ewkb)
        failed=self.client.post(url+"regenerate/",{"lat":54,"lng":-7,"radius_m":250},format="json",HTTP_X_CSRFTOKEN=self.token)
        self.assertEqual(failed.status_code,400)
        original.refresh_from_db();self.assertEqual(bytes(original.path.ewkb),before)

    def test_no_change_regeneration_is_deterministic_and_changed_origin_is_stored(self):
        data=self.create().data;url=f"/api/adventures/{data['id']}/regenerate/"
        same=self.client.post(url,{},format="json",HTTP_X_CSRFTOKEN=self.token)
        self.assertEqual(same.status_code,200,same.data)
        self.assertEqual(same.data["path"],data["path"])
        changed=self.client.post(url,{"lng":-6.259},format="json",HTTP_X_CSRFTOKEN=self.token)
        self.assertEqual(changed.status_code,200,changed.data)
        self.assertAlmostEqual(changed.data["start"]["coordinates"][0],-6.259,places=6)
        self.assertNotEqual(changed.data["path"],data["path"])

    def test_invalid_inputs_do_not_save_adventures(self):
        for invalid in [{"lat":91},{"lng":181},{"lat":"nan"},{"lat":True},{"radius_m":0},{"radius_m":5001},
                        {"stop_count":0},{"stop_count":11},{"categories":[]},{"categories":"heritage"},
                        {"categories":["unknown"]},{"categories":["heritage","heritage"]},{"title":""},{"path":{}}]:
            with self.subTest(invalid=invalid):
                response=self.client.post("/api/adventures/",{**self.payload,**invalid},format="json",HTTP_X_CSRFTOKEN=self.token)
                self.assertEqual(response.status_code,400,response.data)
        for payload in [{},[],"invalid"]:
            self.assertEqual(self.client.post("/api/adventures/",payload,format="json",HTTP_X_CSRFTOKEN=self.token).status_code,400)
        self.assertFalse(Adventure.objects.exists())

    def test_wrong_stop_rename_fields_pagination_and_delete(self):
        first=self.create().data;second=self.create().data
        url=f"/api/adventures/{first['id']}/"
        wrong=self.client.patch(url+f"stops/{second['stops'][0]['id']}/",{"visited":True},format="json",HTTP_X_CSRFTOKEN=self.token)
        self.assertEqual(wrong.status_code,404)
        self.assertEqual(self.client.patch(url,{"radius_m":1000},format="json",HTTP_X_CSRFTOKEN=self.token).status_code,400)
        self.assertEqual(self.client.get("/api/adventures/?page_size=1").data["count"],2)
        self.assertEqual(len(self.client.get("/api/adventures/?page_size=1").data["results"]),1)
        self.assertEqual(self.client.get("/api/adventures/?page_size=51").status_code,400)
        response=self.client.delete(url,HTTP_X_CSRFTOKEN=self.token)
        self.assertEqual(response.status_code,204)
        self.assertFalse(AdventureStop.objects.filter(adventure_id=first["id"]).exists())
        self.assertEqual(Place.objects.count(),6)
        self.assertEqual(self.client.get(url).status_code,404)
        clean=APIClient(enforce_csrf_checks=True)
        self.assertEqual(clean.get("/api/adventures/").data["count"],0)

    def test_failed_regeneration_rolls_back_replaced_stops_and_geometry(self):
        data=self.create().data
        url=f"/api/adventures/{data['id']}/"
        stop_id=data["stops"][0]["id"]
        self.client.patch(url+f"stops/{stop_id}/",{"visited":True},format="json",HTTP_X_CSRFTOKEN=self.token)
        old_ids=list(AdventureStop.objects.filter(adventure_id=data["id"]).values_list("pk",flat=True))
        old_path=bytes(Adventure.objects.get(pk=data["id"]).path.ewkb)
        original_save=AdventureStop.save
        calls=0
        def fail_on_second(instance,*args,**kwargs):
            nonlocal calls
            calls+=1
            if calls==2:
                raise RuntimeError("Synthetic write failure")
            return original_save(instance,*args,**kwargs)
        with patch.object(AdventureStop,"save",new=fail_on_second):
            with self.assertRaises(RuntimeError):
                self.client.post(url+"regenerate/",{"stop_count":3,"confirm_reset":True},format="json",HTTP_X_CSRFTOKEN=self.token)
        self.assertEqual(old_ids,list(AdventureStop.objects.filter(adventure_id=data["id"]).values_list("pk",flat=True)))
        self.assertEqual(old_path,bytes(Adventure.objects.get(pk=data["id"]).path.ewkb))
        self.assertIsNotNone(AdventureStop.objects.get(pk=stop_id).visited_at)


class ImportedAdventureTests(APITestCase):
    def test_real_bundled_data_generates_near_trinity_without_modifying_sources(self):
        for name in ("canvas","public_art","heritage","parks"):
            call_command(f"import_{name}",stdout=io.StringIO(),**({"source_srid":4326} if name=="public_art" else {}))
        client=APIClient(enforce_csrf_checks=True)
        token=client.get("/api/session/").data["csrfToken"]
        payload={"title":"College Green discovery","lat":53.34516502,"lng":-6.258924007,
            "categories":["street_art","heritage","public_art","park"],"radius_m":2000,"stop_count":5}
        response=client.post("/api/adventures/",payload,format="json",HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code,201,response.data)
        self.assertEqual(response.data["progress"]["total"],5)
        self.assertEqual(len({stop["place"]["id"] for stop in response.data["stops"]}),5)
        self.assertEqual({stop["place"]["properties"]["category"] for stop in response.data["stops"]},set(payload["categories"]))
        self.assertNotIn("Thomas Moore Statue",[stop["place"]["properties"]["name"] for stop in response.data["stops"]])
        self.assertTrue(all(stop["distance_from_start_m"]<=2000 for stop in response.data["stops"]))
        with connection.cursor() as cursor:
            cursor.execute("SELECT ST_IsValid(path), ST_SRID(path), ST_NPoints(path) FROM adventures_adventure WHERE id=%s",[response.data["id"]])
            self.assertEqual(cursor.fetchone(),(True,2157,6))
        self.assertEqual((Place.objects.count(),Park.objects.count(),DatasetSource.objects.count()),(922,484,4))
        self.assertTrue(all(stop["place"]["properties"]["source"] for stop in response.data["stops"]))


class SelectionTieTests(APITestCase):
    def test_equal_distance_uses_primary_key_and_radius_is_inclusive(self):
        origin=Point(-6.26,53.35,srid=4326);origin.transform(2157)
        first=Place.objects.create(name="Synthetic first",source_key="first",category="heritage",point=Point(origin.x+250,origin.y,srid=2157))
        Place.objects.create(name="Synthetic tie",source_key="tie",category="heritage",point=Point(origin.x-250,origin.y,srid=2157))
        Place.objects.create(name="Synthetic beyond radius",source_key="far",category="heritage",point=Point(origin.x+251,origin.y,srid=2157))
        generated=generate_adventure(origin,["heritage"],250,1)
        self.assertEqual(generated["stops"][0]["place"].pk,first.pk)
        self.assertAlmostEqual(generated["stops"][0]["distance_from_start_m"],250)
