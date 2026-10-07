from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from core.models import Entity, EntityType, Event, Project
from squiggle_automation.testutils import random_password

User = get_user_model()

SCHEMA = {
    "type": "object",
    "properties": {"address": {"type": "string"}, "comment": {"type": "string"}},
    "required": ["address"],
}


class EntityApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("apiuser", password=random_password())
        self.token = Token.objects.create(user=self.user)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")

        # entity types must exist before the project so that the upsert index is created for them
        self.entitytype = EntityType.objects.create(name="host", schema=SCHEMA, identifier_keys="address")
        self.approval_type = EntityType.objects.create(
            name="approved-host", schema=SCHEMA, identifier_keys="address", approval_required=True
        )
        self.project = Project.objects.create(name="project-1")
        self.other_project = Project.objects.create(name="project-2")

    def url(self, entitytype="host", project=None):
        return reverse(
            "api:entity-list",
            kwargs={"project": (project or self.project).pk, "entitytype": entitytype},
        )

    def test_unauthenticated_request_is_rejected(self):
        self.assertEqual(APIClient().get(self.url()).status_code, 401)
        self.assertEqual(APIClient().put(self.url(), {"data": {}}, format="json").status_code, 401)

    def test_unknown_project_or_entitytype_is_404(self):
        self.assertEqual(self.client.get(self.url(project=Project(pk=999999))).status_code, 404)
        self.assertEqual(self.client.get(self.url("nope")).status_code, 404)
        r = self.client.put(self.url(project=Project(pk=999999)), {"data": {"address": "a"}}, format="json")
        self.assertEqual(r.status_code, 404)
        r = self.client.put(self.url("nope"), {"data": {"address": "a"}}, format="json")
        self.assertEqual(r.status_code, 404)

    def test_put_creates_entity(self):
        r = self.client.put(self.url(), {"data": {"address": "1.1.1.1"}}, format="json")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json(), {"data": {"address": "1.1.1.1"}, "state": "enabled"})
        entity = Entity.objects.get(project=self.project, entitytype=self.entitytype)
        self.assertEqual(entity.data, {"address": "1.1.1.1"})
        self.assertEqual(Event.objects.filter(entity=entity).count(), 1)

    def test_put_existing_entity_merges_data_and_keeps_state(self):
        self.client.put(self.url(), {"data": {"address": "1.1.1.1"}}, format="json")
        Entity.objects.update(state=Entity.STATE_DISABLED)

        r = self.client.put(self.url(), {"data": {"address": "1.1.1.1", "comment": "hi"}}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"data": {"address": "1.1.1.1", "comment": "hi"}, "state": "disabled"})
        self.assertEqual(Entity.objects.count(), 1)

    def test_put_ignores_state_in_body(self):
        r = self.client.put(
            self.url("approved-host"), {"data": {"address": "1.1.1.1"}, "state": "enabled"}, format="json"
        )
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()["state"], "waiting_approval")
        self.assertEqual(Event.objects.count(), 0)

    def test_put_rejects_invalid_data(self):
        for data in (
            {"comment": "no identifier"},
            {"address": 5},
            "not an object",
            None,
        ):
            r = self.client.put(self.url(), {"data": data}, format="json")
            self.assertEqual(r.status_code, 400, data)
        r = self.client.put(self.url(), {}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(Entity.objects.count(), 0)

    def test_get_lists_only_entities_of_project_and_type(self):
        self.client.put(self.url(), {"data": {"address": "2.2.2.2"}}, format="json")
        self.client.put(self.url(), {"data": {"address": "1.1.1.1"}}, format="json")
        self.client.put(self.url(project=self.other_project), {"data": {"address": "3.3.3.3"}}, format="json")
        self.client.put(self.url("approved-host"), {"data": {"address": "4.4.4.4"}}, format="json")

        r = self.client.get(self.url())
        self.assertEqual(r.status_code, 200)
        self.assertEqual(
            r.json(),
            [
                {"data": {"address": "1.1.1.1"}, "state": "enabled"},
                {"data": {"address": "2.2.2.2"}, "state": "enabled"},
            ],
        )

    def test_get_state_filter(self):
        self.client.put(self.url(), {"data": {"address": "1.1.1.1"}}, format="json")
        self.client.put(self.url(), {"data": {"address": "2.2.2.2"}}, format="json")
        Entity.objects.filter(data__address="2.2.2.2").update(state=Entity.STATE_DISABLED)

        r = self.client.get(self.url(), {"state": "disabled"})
        self.assertEqual(r.json(), [{"data": {"address": "2.2.2.2"}, "state": "disabled"}])
        r = self.client.get(self.url(), {"state": "enabled"})
        self.assertEqual(r.json(), [{"data": {"address": "1.1.1.1"}, "state": "enabled"}])
        r = self.client.get(self.url(), {"state": "waiting_approval"})
        self.assertEqual(r.json(), [])

    def test_get_unknown_state_is_400(self):
        self.assertEqual(self.client.get(self.url(), {"state": "bogus"}).status_code, 400)

    def test_export_can_be_imported_again(self):
        self.client.put(self.url(), {"data": {"address": "1.1.1.1", "comment": "x"}}, format="json")
        exported = self.client.get(self.url()).json()
        Entity.objects.all().delete()

        for item in exported:
            self.assertEqual(self.client.put(self.url(), item, format="json").status_code, 201)
        self.assertEqual(self.client.get(self.url()).json(), exported)
