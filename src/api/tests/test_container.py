from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from core.models import ConfigOption, Container
from squiggle_automation.testutils import random_password

User = get_user_model()


class ContainerApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("apiuser", password=random_password())
        self.token = Token.objects.create(user=self.user)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")

    def test_unauthenticated_request_is_rejected(self):
        anon_client = APIClient()
        r = anon_client.get(reverse("api:container-list"))
        self.assertEqual(r.status_code, 401)

    def test_list_containers(self):
        Container.objects.create(name="container-a", image="alpine")
        Container.objects.create(name="container-b", image="alpine")

        r = self.client.get(reverse("api:container-list"))
        self.assertEqual(r.status_code, 200)

        names = [c["name"] for c in r.data]
        self.assertIn("container-a", names)
        self.assertIn("container-b", names)

    def test_retrieve_container(self):
        container = Container.objects.create(name="container-retrieve", image="alpine")

        r = self.client.get(reverse("api:container-detail", args=[container.name]))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["name"], "container-retrieve")
        self.assertEqual(r.data["image_tag"], "latest")
        self.assertNotIn("id", r.data)

    def test_create_container(self):
        r = self.client.post(
            reverse("api:container-list"),
            {
                "name": "new-container",
                "image": "alpine",
                "image_tag": "3.20",
                "cap_net_raw": True,
                "net_host": True,
            },
            format="json",
        )
        self.assertEqual(r.status_code, 201, r.content)

        container = Container.objects.get(name="new-container")
        self.assertEqual(container.image_tag, "3.20")
        self.assertTrue(container.cap_net_raw)
        self.assertTrue(container.net_host)

    def test_create_container_with_configoptions(self):
        option = ConfigOption.objects.create(name="opt")

        r = self.client.post(
            reverse("api:container-list"),
            {"name": "container-with-options", "image": "alpine", "configoptions": [option.name]},
            format="json",
        )
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.data["configoptions"], [option.name])

        container = Container.objects.get(name="container-with-options")
        self.assertEqual(list(container.configoptions.all()), [option])

    def test_create_container_with_unknown_configoption_name_is_rejected(self):
        r = self.client.post(
            reverse("api:container-list"),
            {"name": "container-bad-option", "image": "alpine", "configoptions": ["does-not-exist"]},
            format="json",
        )
        self.assertEqual(r.status_code, 400)
        self.assertFalse(Container.objects.filter(name="container-bad-option").exists())

    @override_settings(CONTAINER_MOUNT_ALLOWED_HOST_PATHS=["/srv/"])
    def test_create_container_with_mounts(self):
        r = self.client.post(
            reverse("api:container-list"),
            {"name": "container-with-mounts", "image": "alpine", "mounts": {"/srv/wordlists": "/data/wordlists"}},
            format="json",
        )
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.data["mounts"], {"/srv/wordlists": "/data/wordlists"})

        container = Container.objects.get(name="container-with-mounts")
        self.assertEqual(container.mounts, {"/srv/wordlists": "/data/wordlists"})

    def test_create_container_without_mounts_defaults_to_empty_object(self):
        r = self.client.post(
            reverse("api:container-list"), {"name": "container-no-mounts", "image": "alpine"}, format="json"
        )
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.data["mounts"], {})

    @override_settings(CONTAINER_MOUNT_ALLOWED_HOST_PATHS=["/srv/"])
    def test_create_container_with_invalid_mounts_is_rejected(self):
        r = self.client.post(
            reverse("api:container-list"),
            {"name": "container-bad-mounts", "image": "alpine", "mounts": {"/srv/wordlists": "/data/tmp"}},
            format="json",
        )
        self.assertEqual(r.status_code, 400)
        self.assertIn("mounts", r.data)
        self.assertFalse(Container.objects.filter(name="container-bad-mounts").exists())

    def test_update_container(self):
        container = Container.objects.create(name="to-update", image="alpine")

        r = self.client.patch(
            reverse("api:container-detail", args=[container.name]),
            {"image_tag": "edge"},
            format="json",
        )
        self.assertEqual(r.status_code, 200, r.content)

        container.refresh_from_db()
        self.assertEqual(container.image_tag, "edge")

    def test_delete_container(self):
        container = Container.objects.create(name="to-delete", image="alpine")

        r = self.client.delete(reverse("api:container-detail", args=[container.name]))
        self.assertEqual(r.status_code, 204)
        self.assertFalse(Container.objects.filter(pk=container.pk).exists())
