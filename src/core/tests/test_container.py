import json

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
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
        container = Container.objects.create(
            name="c-json", image="image", cap_net_raw=True, net_host=True, mounts={"/srv/w": "/data/w"}
        )

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
        self.assertEqual(container.mounts, {})

    @override_settings(CONTAINER_MOUNT_ALLOWED_HOST_PATHS=["/srv/"])
    def test_post_creates_container_with_mounts(self):
        r = self.client.post(
            reverse("core:container-create"),
            {
                "name": "with-mounts",
                "image": "image",
                "image_tag": "latest",
                "mounts": json.dumps({"/srv/wordlists": "/data/wordlists"}),
            },
        )
        self.assertEqual(r.status_code, 302)

        container = Container.objects.get(name="with-mounts")
        self.assertEqual(container.mounts, {"/srv/wordlists": "/data/wordlists"})

    def test_post_with_empty_mounts_field_stores_empty_object(self):
        r = self.client.post(
            reverse("core:container-create"),
            {"name": "empty-mounts", "image": "image", "image_tag": "latest", "mounts": ""},
        )
        self.assertEqual(r.status_code, 302)

        container = Container.objects.get(name="empty-mounts")
        self.assertEqual(container.mounts, {})

    @override_settings(CONTAINER_MOUNT_ALLOWED_HOST_PATHS=["/srv/"])
    def test_post_with_invalid_mounts_shows_error(self):
        r = self.client.post(
            reverse("core:container-create"),
            {
                "name": "bad-mounts",
                "image": "image",
                "image_tag": "latest",
                "mounts": json.dumps({"/srv/wordlists": "/data/input"}),
            },
        )
        self.assertEqual(r.status_code, 200)
        self.assertIn("mounts", r.context["form"].errors)
        self.assertFalse(Container.objects.filter(name="bad-mounts").exists())


@override_settings(CONTAINER_MOUNT_ALLOWED_HOST_PATHS=["/srv/", "/opt/wordlists"])
class ContainerMountsValidationTests(TestCase):
    def assert_valid(self, mounts):
        Container(name="c", image="image", mounts=mounts).clean()

    def assert_invalid(self, mounts, message=None):
        container = Container(name="c", image="image", mounts=mounts)
        with self.assertRaises(ValidationError) as cm:
            container.clean()
        self.assertIn("mounts", cm.exception.message_dict)
        if message:
            self.assertIn(message, cm.exception.message_dict["mounts"])

    def assert_host_path_not_allowed(self, host_path):
        self.assert_invalid(
            {host_path: "/data/mounted"},
            f'"{host_path}" is not below an allowed host path (/srv/, /opt/wordlists).',
        )

    def test_not_an_object(self):
        self.assert_invalid(["/srv/wordlists"])

    def test_container_path_not_a_string(self):
        self.assert_invalid({"/srv/wordlists": 1})

    def test_relative_paths(self):
        self.assert_invalid({"srv/wordlists": "/data/wordlists"})
        self.assert_invalid({"/srv/wordlists": "data/wordlists"})

    def test_colon_in_path(self):
        self.assert_invalid({"/srv/wordlists": "/data/wordlists:rw"})

    def test_dotdot_in_path(self):
        self.assert_invalid({"/srv/../etc": "/data/wordlists"})
        self.assert_invalid({"/srv/wordlists": "/data/x/../input"})

    def test_root_as_container_path(self):
        self.assert_invalid({"/srv/wordlists": "/"})

    def test_reserved_container_paths(self):
        self.assert_invalid({"/srv/wordlists": "/data/input"})
        self.assert_invalid({"/srv/wordlists": "/data/tmp/"})
        self.assert_invalid({"/srv/wordlists": "/data/output/wordlists"})
        self.assert_invalid({"/srv/wordlists": "/data"})

    def test_reserved_prefix_without_separator_is_allowed(self):
        self.assert_valid({"/srv/wordlists": "/data/inputs"})

    def test_duplicate_container_path(self):
        self.assert_invalid({"/srv/a": "/data/wordlists", "/srv/b": "/data/wordlists/"})

    def test_all_problems_are_reported(self):
        container = Container(
            name="c", image="image", mounts={"/etc": "/data/input", "relative": "/data/x", "/srv/w": "/"}
        )
        with self.assertRaises(ValidationError) as cm:
            container.clean()
        self.assertEqual(
            cm.exception.message_dict["mounts"],
            [
                '"/etc" is not below an allowed host path (/srv/, /opt/wordlists).',
                '"/data/input" overlaps with "/data/input", which is used by the platform.',
                '"relative" must be an absolute path without ":" or "..".',
                'Cannot mount to "/".',
            ],
        )

    def test_paths_below_allowed_paths(self):
        self.assert_valid({"/srv/wordlists": "/data/wordlists", "/srv/secrets/secret.yaml": "/opt/secrets.yaml"})
        self.assert_valid({"/opt/wordlists/big.txt": "/data/big.txt"})

    def test_allowed_paths_themselves(self):
        self.assert_valid({"/srv": "/data/mounted"})
        self.assert_valid({"/srv/": "/data/mounted"})
        self.assert_valid({"/opt/wordlists": "/data/mounted"})

    def test_other_paths(self):
        self.assert_host_path_not_allowed("/etc")
        self.assert_host_path_not_allowed("/")
        self.assert_host_path_not_allowed("/opt")

    def test_sibling_with_same_prefix(self):
        self.assert_host_path_not_allowed("/srv2/wordlists")
        self.assert_host_path_not_allowed("/opt/wordlists-other")

    def test_double_slashes_are_normalized(self):
        self.assert_valid({"/srv//wordlists": "/data/mounted"})

    @override_settings(CONTAINER_MOUNT_ALLOWED_HOST_PATHS=["/"])
    def test_root_allows_everything(self):
        self.assert_valid({"/etc": "/data/mounted"})

    @override_settings(CONTAINER_MOUNT_ALLOWED_HOST_PATHS=[])
    def test_unset_disables_mounts(self):
        self.assert_invalid(
            {"/srv/wordlists": "/data/mounted"},
            "Mounts are disabled, as CONTAINER_MOUNT_ALLOWED_HOST_PATHS is not set.",
        )

    @override_settings(CONTAINER_MOUNT_ALLOWED_HOST_PATHS=[])
    def test_unset_still_allows_containers_without_mounts(self):
        self.assert_valid({})


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
