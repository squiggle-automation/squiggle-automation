import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils.html import escape

from api.serializers import ContainerSerializer
from squiggle_automation.testutils import random_password

from ..models import Container, Executor

User = get_user_model()


class ContainerTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("plain", password=random_password())
        self.client.force_login(self.user)


class ContainerListViewTests(ContainerTestCase):
    def test_anonymous_redirected_to_login(self):
        self.client.logout()

        r = self.client.get(reverse("core:containers"))
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login/", r.url)

    def test_lists_containers(self):
        Container.objects.create(name="c-b", image="image-b")
        Container.objects.create(name="c-a", image="image-a")

        r = self.client.get(reverse("core:containers"))
        self.assertEqual(r.status_code, 200)

        names = [c.name for c in r.context["containers"]]
        self.assertEqual(names, ["c-a", "c-b"])

    def test_shows_json_matching_the_api_serializer(self):
        container = Container.objects.create(name="c-json", image="image", cap_net_raw=True, net_host=True)

        r = self.client.get(reverse("core:containers"))
        self.assertEqual(r.status_code, 200)

        expected_json = json.dumps(ContainerSerializer(container).data, indent=2)
        self.assertContains(r, escape(expected_json))
        self.assertContains(r, f'data-bs-target="#container-json-{container.pk}"')
        self.assertContains(r, f'id="container-json-{container.pk}-content"')

    def test_json_modal_has_no_configvalue_note(self):
        # containers don't hold config values themselves, unlike configoptions/executors
        Container.objects.create(name="c-json-note", image="image")

        r = self.client.get(reverse("core:containers"))

        self.assertNotContains(r, "Config values are not included here")


class ContainerCreateViewTests(ContainerTestCase):
    def test_get_ok(self):
        r = self.client.get(reverse("core:container-create"))
        self.assertEqual(r.status_code, 200)

    def test_post_creates_container(self):
        r = self.client.post(
            reverse("core:container-create"),
            {
                "name": "my-container",
                "image": "myrepo/image",
                "image_tag": "1.0",
                "cap_net_raw": "on",
                "net_host": "on",
            },
        )
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.url, reverse("core:containers"))

        container = Container.objects.get(name="my-container")
        self.assertEqual(container.image, "myrepo/image")
        self.assertEqual(container.image_tag, "1.0")
        self.assertTrue(container.cap_net_raw)
        self.assertTrue(container.net_host)


class ContainerUpdateViewTests(ContainerTestCase):
    def setUp(self):
        super().setUp()
        self.container = Container.objects.create(name="original", image="image")

    def test_get_ok(self):
        r = self.client.get(reverse("core:container-update", args=[self.container.pk]))
        self.assertEqual(r.status_code, 200)

    def test_post_updates_container(self):
        r = self.client.post(
            reverse("core:container-update", args=[self.container.pk]),
            {
                "name": "renamed",
                "image": "image",
                "image_tag": "latest",
                "cap_net_raw": "on",
                "net_host": "on",
            },
        )
        self.assertEqual(r.status_code, 302)

        self.container.refresh_from_db()
        self.assertEqual(self.container.name, "renamed")
        self.assertTrue(self.container.cap_net_raw)
        self.assertTrue(self.container.net_host)


class ContainerDeleteViewTests(ContainerTestCase):
    def test_get_shows_confirmation_and_cascade_warning(self):
        container = Container.objects.create(name="to-delete", image="image")

        r = self.client.get(reverse("core:container-delete", args=[container.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "to-delete")
        self.assertContains(r, "This will delete all executors that use this container")

    def test_post_deletes_container(self):
        container = Container.objects.create(name="to-delete2", image="image")

        r = self.client.post(reverse("core:container-delete", args=[container.pk]))
        self.assertEqual(r.status_code, 302)
        self.assertFalse(Container.objects.filter(pk=container.pk).exists())

    def test_post_cascades_delete_to_executors_using_the_container(self):
        container = Container.objects.create(name="to-delete3", image="image")
        executor = Executor.objects.create(name="uses-container", container=container)

        r = self.client.post(reverse("core:container-delete", args=[container.pk]))
        self.assertEqual(r.status_code, 302)

        self.assertFalse(Container.objects.filter(pk=container.pk).exists())
        self.assertFalse(Executor.objects.filter(pk=executor.pk).exists())

    def test_post_does_not_affect_executors_using_a_different_container(self):
        container = Container.objects.create(name="to-delete4", image="image")
        other_container = Container.objects.create(name="keep", image="image")
        other_executor = Executor.objects.create(name="unaffected", container=other_container)

        self.client.post(reverse("core:container-delete", args=[container.pk]))

        self.assertTrue(Executor.objects.filter(pk=other_executor.pk).exists())
