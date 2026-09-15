from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.http import QueryDict
from django.test import TestCase
from django.urls import reverse

from squiggle_automation.testutils import random_password

from ..forms.widgets import JedisonWidget
from ..models import Entity, EntityType, Event, Project

User = get_user_model()

SCHEMA = {"type": "object", "properties": {"address": {"type": "string"}}}


class EntityTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("plain", password=random_password())
        self.client.force_login(self.user)

        # entitytype must exist before the projects so that upsert/index creation works (see EntityType.save())
        self.entitytype = EntityType.objects.create(name="host", schema=SCHEMA, identifier_keys="address")
        self.project = Project.objects.create(name="project-1")
        # created upfront (rather than ad hoc in tests) so that no test needs to CREATE INDEX (via Project.save())
        # in the same transaction as an already-inserted Entity row, which postgres rejects
        self.other_project = Project.objects.create(name="project-2")


class EntityOverviewViewTests(EntityTestCase):
    def test_anonymous_redirected_to_login(self):
        self.client.logout()

        r = self.client.get(reverse("core:entities", kwargs={"project": self.project.pk}))
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login/", r.url)

    def test_shows_entity_counts_per_entitytype(self):
        # create the entitytype (which creates its unique index on core_entity via a DDL statement)
        # before inserting into core_entity below - postgres refuses to run DDL on a table within the
        # same transaction as a preceding DML statement on that same table ("pending trigger events")
        other_entitytype = EntityType.objects.create(name="empty-type", schema=SCHEMA, identifier_keys="address")

        Entity.objects.create(
            entitytype=self.entitytype, project=self.project, data={"address": "1.1.1.1"}, state=Entity.STATE_ENABLED
        )
        Entity.objects.create(
            entitytype=self.entitytype, project=self.project, data={"address": "2.2.2.2"}, state=Entity.STATE_ENABLED
        )

        r = self.client.get(reverse("core:entities", kwargs={"project": self.project.pk}))
        self.assertEqual(r.status_code, 200)

        counts = {e.pk: e.count for e in r.context["entitytypes"]}
        self.assertEqual(counts[self.entitytype.pk], 2)
        self.assertEqual(counts[other_entitytype.pk], 0)

    def test_shows_entity_counts_broken_down_by_state_per_entitytype(self):
        other_entitytype = EntityType.objects.create(name="empty-type", schema=SCHEMA, identifier_keys="address")

        states = [Entity.STATE_ENABLED, Entity.STATE_ENABLED, Entity.STATE_WAITING_APPROVAL, Entity.STATE_DISABLED]
        for i, state in enumerate(states):
            Entity.objects.create(
                entitytype=self.entitytype, project=self.project, data={"address": f"1.1.1.{i}"}, state=state
            )
        # a different project must not contribute to the counts
        Entity.objects.create(
            entitytype=self.entitytype,
            project=self.other_project,
            data={"address": "2.2.2.2"},
            state=Entity.STATE_ENABLED,
        )

        r = self.client.get(reverse("core:entities", kwargs={"project": self.project.pk}))
        self.assertEqual(r.status_code, 200)

        entitytypes = {e.pk: e for e in r.context["entitytypes"]}
        counted = entitytypes[self.entitytype.pk]
        self.assertEqual(counted.count, 4)
        self.assertEqual(counted.count_active, 2)
        self.assertEqual(counted.count_waiting, 1)
        self.assertEqual(counted.count_disabled, 1)

        empty = entitytypes[other_entitytype.pk]
        self.assertEqual(empty.count, 0)
        self.assertEqual(empty.count_active, 0)
        self.assertEqual(empty.count_waiting, 0)
        self.assertEqual(empty.count_disabled, 0)


class EntityListViewTests(EntityTestCase):
    def test_unknown_entitytype_is_404(self):
        r = self.client.get(reverse("core:entity-list", kwargs={"project": self.project.pk, "entitytype": "nope"}))
        self.assertEqual(r.status_code, 404)

    def test_lists_only_entities_of_the_given_type_and_project(self):
        other_entitytype = EntityType.objects.create(name="other-type", schema=SCHEMA, identifier_keys="address")

        matching = Entity.objects.create(
            entitytype=self.entitytype, project=self.project, data={"address": "1.1.1.1"}, state=Entity.STATE_ENABLED
        )
        Entity.objects.create(
            entitytype=self.entitytype,
            project=self.other_project,
            data={"address": "2.2.2.2"},
            state=Entity.STATE_ENABLED,
        )
        Entity.objects.create(
            entitytype=other_entitytype,
            project=self.project,
            data={"address": "3.3.3.3"},
            state=Entity.STATE_ENABLED,
        )

        r = self.client.get(
            reverse("core:entity-list", kwargs={"project": self.project.pk, "entitytype": self.entitytype.name})
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(list(r.context["entities"]), [matching])

    def test_approve_form_carries_the_current_querystring(self):
        waiting_entity = Entity.objects.create(
            entitytype=self.entitytype,
            project=self.project,
            data={"address": "1.1.1.1"},
            state=Entity.STATE_WAITING_APPROVAL,
        )

        list_url = reverse("core:entity-list", kwargs={"project": self.project.pk, "entitytype": self.entitytype.name})
        r = self.client.get(f"{list_url}?s=-address")
        self.assertEqual(r.status_code, 200)

        approve_url = reverse("core:entity-approve", kwargs={"project": self.project.pk, "pk": waiting_entity.pk})
        self.assertContains(r, f'action="{approve_url}?s=-address"')


class EntityListColumnTests(EntityTestCase):
    """The columns of the entity list come from the schema of the entity type, see EntityListView."""

    def setUp(self):
        super().setUp()

        # a schema with more than just the identifier key, so a selection can be tested
        self.entitytype = EntityType.objects.create(
            name="service",
            schema={
                "type": "object",
                "required": ["address", "port"],
                "properties": {
                    "address": {"type": "string"},
                    "port": {"type": "number"},
                    "service": {"type": "string"},
                },
            },
            identifier_keys="address,port",
        )

    def url(self, query=""):
        url = reverse("core:entity-list", kwargs={"project": self.project.pk, "entitytype": self.entitytype.name})

        return f"{url}?{query}" if query else url

    def create_entity(self):
        return Entity.objects.create(
            entitytype=self.entitytype,
            project=self.project,
            data={"address": "1.1.1.1", "port": 80, "service": "nginx"},
            state=Entity.STATE_ENABLED,
        )

    def test_picker_offers_the_schema_keys(self):
        r = self.client.get(self.url())

        # identifier keys first, then the other required ones, then the rest
        self.assertEqual([i["key"] for i in r.context["column_options"]], ["address", "port", "service"])

    def test_default_columns_are_the_identifier_keys(self):
        self.create_entity()

        r = self.client.get(self.url())

        self.assertEqual(r.context["columns"], ["address", "port"])
        self.assertEqual(list(r.context["entities"])[0].cells, ["1.1.1.1", 80])

    def test_columns_can_be_selected(self):
        self.create_entity()

        r = self.client.get(self.url("c=address&c=service"))

        self.assertEqual(r.context["columns"], ["address", "service"])
        self.assertEqual(list(r.context["entities"])[0].cells, ["1.1.1.1", "nginx"])

    def test_columns_keep_the_schema_order_however_they_were_picked(self):
        self.create_entity()

        r = self.client.get(self.url("c=service&c=address"))

        # not the order of the parameters, which is the order the picker was clicked in
        self.assertEqual(r.context["columns"], ["address", "service"])
        self.assertEqual(list(r.context["entities"])[0].cells, ["1.1.1.1", "nginx"])

    def test_picker_marks_the_shown_columns(self):
        r = self.client.get(self.url("c=service"))

        shown = {i["key"]: i["shown"] for i in r.context["column_options"]}
        self.assertEqual(shown, {"address": False, "port": False, "service": True})

    def test_picker_adds_a_column_without_dropping_the_default_ones(self):
        r = self.client.get(self.url())

        # the defaults are not in the url, so the link has to spell them out
        urls = {i["key"]: i["url"] for i in r.context["column_options"]}
        self.assertEqual(urls["service"], f"{self.url()}?c=address&c=port&c=service")

        r = self.client.get(urls["service"])
        self.assertEqual(r.context["columns"], ["address", "port", "service"])

    def test_picker_removes_a_shown_column(self):
        r = self.client.get(self.url("c=address&c=service"))

        urls = {i["key"]: i["url"] for i in r.context["column_options"]}
        self.assertEqual(urls["address"], f"{self.url()}?c=service")

        r = self.client.get(urls["address"])
        self.assertEqual(r.context["columns"], ["service"])

    def test_picker_link_drops_the_page_but_keeps_other_parameters(self):
        r = self.client.get(self.url("page=1&keep=me"))

        urls = {i["key"]: i["url"] for i in r.context["column_options"]}
        self.assertEqual(urls["service"], f"{self.url()}?keep=me&c=address&c=port&c=service")

    def test_unknown_column_is_ignored(self):
        self.create_entity()

        r = self.client.get(self.url("c=nope"))

        self.assertEqual(r.context["columns"], ["address", "port"])

    def test_missing_value_renders_as_a_placeholder(self):
        Entity.objects.create(
            entitytype=self.entitytype,
            project=self.project,
            data={"address": "1.1.1.1", "port": 80},
            state=Entity.STATE_ENABLED,
        )

        r = self.client.get(self.url("c=service"))

        self.assertEqual(list(r.context["entities"])[0].cells, [None])
        self.assertContains(r, "<td>-</td>", html=True)

    def test_htmx_request_renders_only_the_table(self):
        self.create_entity()

        r = self.client.get(self.url(), headers={"hx-request": "true"})

        self.assertEqual(r.status_code, 200)
        self.assertTemplateUsed(r, "core/entity_list_content.html")
        self.assertNotContains(r, "<aside")
        # the picker is part of the swapped content, otherwise its check marks would not update
        self.assertContains(r, "bi-check-square")

    def test_history_restore_renders_the_full_page(self):
        self.create_entity()

        r = self.client.get(self.url(), headers={"hx-request": "true", "hx-history-restore-request": "true"})

        self.assertEqual(r.status_code, 200)
        self.assertTemplateUsed(r, "core/entity_list.html")
        self.assertContains(r, "<aside")


class EntityListSortTests(EntityTestCase):
    """Sorting of the entity list, see EntityListView.get_sort()/EntityQuerySet.order_entity_by_values()."""

    def setUp(self):
        super().setUp()

        self.entitytype = EntityType.objects.create(
            name="service",
            schema={
                "type": "object",
                "properties": {
                    "address": {"type": "string"},
                    "port": {"type": "number"},
                    "service": {"type": "string"},
                },
            },
            identifier_keys="address",
        )

    def url(self, query=""):
        url = reverse("core:entity-list", kwargs={"project": self.project.pk, "entitytype": self.entitytype.name})

        return f"{url}?{query}" if query else url

    def create_entities(self):
        # the services sort differently as text than the ports do as numbers, so a mix-up of the
        # two orderings cannot pass unnoticed. the text values are letters only on purpose - with
        # punctuation in them the expected order would depend on the collation of the database
        for address, port, service in [("hostc", 443, "ssh"), ("hosta", 80, "http"), ("hostb", 8080, "nginx")]:
            Entity.objects.create(
                entitytype=self.entitytype,
                project=self.project,
                data={"address": address, "port": port, "service": service},
                state=Entity.STATE_ENABLED,
            )

    def addresses(self, response):
        return [i.data["address"] for i in response.context["entities"]]

    def test_default_sorting_is_by_the_identifier_keys(self):
        self.create_entities()

        r = self.client.get(self.url())

        self.assertEqual(r.context["sort_key"], None)
        self.assertEqual(self.addresses(r), ["hosta", "hostb", "hostc"])

    def test_sort_ascending_by_another_key(self):
        self.create_entities()

        r = self.client.get(self.url("c=service&s=service"))

        self.assertEqual(r.context["sort_key"], "service")
        self.assertFalse(r.context["sort_descending"])
        # http, nginx, ssh
        self.assertEqual(self.addresses(r), ["hosta", "hostb", "hostc"])

    def test_sort_descending_reverses_the_order(self):
        self.create_entities()

        r = self.client.get(self.url("s=-address"))

        self.assertTrue(r.context["sort_descending"])
        self.assertEqual(self.addresses(r), ["hostc", "hostb", "hosta"])

    def test_a_number_key_sorts_numerically_and_not_as_text(self):
        self.create_entities()

        r = self.client.get(self.url("c=port&s=port"))

        # as text this would be 443, 80, 8080
        self.assertEqual([i.data["port"] for i in r.context["entities"]], [80, 443, 8080])

    def test_unknown_sort_key_falls_back_to_the_default(self):
        self.create_entities()

        r = self.client.get(self.url("s=nope"))

        self.assertEqual(r.context["sort_key"], None)
        self.assertEqual(self.addresses(r), ["hosta", "hostb", "hostc"])

    def test_header_links_sort_ascending_and_flip_to_descending(self):
        r = self.client.get(self.url("c=address"))

        header = r.context["column_headers"][0]
        self.assertFalse(header["sorted"])
        self.assertEqual(header["url"], f"{self.url()}?c=address&s=address")

        # following it sorts ascending, and offers descending next
        r = self.client.get(header["url"])
        header = r.context["column_headers"][0]
        self.assertTrue(header["sorted"])
        self.assertFalse(header["descending"])
        self.assertEqual(header["url"], f"{self.url()}?c=address&s=-address")

        r = self.client.get(header["url"])
        header = r.context["column_headers"][0]
        self.assertTrue(header["descending"])
        # and back to ascending
        self.assertEqual(header["url"], f"{self.url()}?c=address&s=address")

    def test_sorting_keeps_the_filters_and_drops_the_page(self):
        r = self.client.get(self.url("c=address&f_address=1.1&page=1"))

        self.assertEqual(r.context["column_headers"][0]["url"], f"{self.url()}?c=address&f_address=1.1&s=address")

    def test_pages_do_not_repeat_rows_when_sorted_by_a_key_with_equal_values(self):
        # same value in the sorted column everywhere, so only the tiebreaker of
        # order_entity_by_values() decides the order of these rows
        for address in ["1.1.1.1", "2.2.2.2", "3.3.3.3", "4.4.4.4"]:
            Entity.objects.create(
                entitytype=self.entitytype,
                project=self.project,
                data={"address": address, "service": "http"},
                state=Entity.STATE_ENABLED,
            )

        queryset = Entity.objects.filter(project=self.project, entitytype=self.entitytype).order_entity_by_values(
            self.entitytype, keys=["service"]
        )

        # two "pages" of two rows each have to be four different rows - without the tiebreaker
        # of order_entity_by_values() the database may return a row on both pages, or on neither
        first = [i.pk for i in queryset[:2]]
        second = [i.pk for i in queryset[2:4]]

        self.assertEqual(len(set(first + second)), 4)


class EntityListFilterTests(EntityTestCase):
    """Filtering and searching of the entity list, see EntityListView.get_column_filters()."""

    def setUp(self):
        super().setUp()

        self.entitytype = EntityType.objects.create(
            name="service",
            schema={
                "type": "object",
                "properties": {
                    "address": {"type": "string"},
                    "port": {"type": "number"},
                    "service": {"type": "string"},
                },
            },
            identifier_keys="address",
        )

        self.nginx = Entity.objects.create(
            entitytype=self.entitytype,
            project=self.project,
            data={"address": "1.1.1.1", "port": 80, "service": "nginx"},
            state=Entity.STATE_ENABLED,
        )
        self.apache = Entity.objects.create(
            entitytype=self.entitytype,
            project=self.project,
            data={"address": "2.2.2.2", "port": 8080, "service": "Apache"},
            state=Entity.STATE_WAITING_APPROVAL,
        )

    def url(self, query=""):
        url = reverse("core:entity-list", kwargs={"project": self.project.pk, "entitytype": self.entitytype.name})

        return f"{url}?{query}" if query else url

    def test_column_filter_matches_a_substring(self):
        r = self.client.get(self.url("f_service=ngin"))

        self.assertEqual(list(r.context["entities"]), [self.nginx])

    def test_column_filter_is_case_insensitive(self):
        r = self.client.get(self.url("f_service=apache"))

        self.assertEqual(list(r.context["entities"]), [self.apache])

    def test_column_filter_works_on_a_number_key(self):
        # data->>'port' renders the number as text, so this is a substring match on "8080"
        r = self.client.get(self.url("f_port=8080"))

        self.assertEqual(list(r.context["entities"]), [self.apache])

    def test_several_column_filters_are_combined_with_and(self):
        r = self.client.get(self.url("f_service=a&f_address=2.2"))
        self.assertEqual(list(r.context["entities"]), [self.apache])

        # both have to match
        r = self.client.get(self.url("f_service=nginx&f_address=2.2"))
        self.assertEqual(list(r.context["entities"]), [])

    def test_empty_and_unknown_column_filters_are_ignored(self):
        r = self.client.get(self.url("f_service=&f_nope=xxx"))

        self.assertEqual(r.context["column_filters"], {})
        self.assertEqual(len(r.context["entities"]), 2)

    def test_column_filter_value_is_rendered_back_into_the_input(self):
        r = self.client.get(self.url("c=service&f_service=ngin"))

        header = r.context["column_headers"][0]
        self.assertEqual(header["filter_name"], "f_service")
        self.assertEqual(header["filter_value"], "ngin")
        self.assertContains(r, 'name="f_service"')
        self.assertContains(r, 'value="ngin"')

    def test_search_looks_in_every_schema_key(self):
        # the term is in a key that is not even a shown column
        r = self.client.get(self.url("c=address&q=nginx"))

        self.assertEqual(list(r.context["entities"]), [self.nginx])

    def test_search_matches_any_of_the_keys(self):
        r = self.client.get(self.url("q=2.2"))

        self.assertEqual(list(r.context["entities"]), [self.apache])

    def test_search_and_column_filter_are_combined(self):
        r = self.client.get(self.url("q=nginx&f_port=8080"))

        self.assertEqual(list(r.context["entities"]), [])

    def test_state_can_be_filtered(self):
        r = self.client.get(self.url(f"state={Entity.STATE_WAITING_APPROVAL}"))

        self.assertEqual(r.context["state_filter"], Entity.STATE_WAITING_APPROVAL)
        self.assertEqual(list(r.context["entities"]), [self.apache])

    def test_invalid_state_is_ignored(self):
        for query in ["state=nope", "state=99", "state="]:
            r = self.client.get(self.url(query))

            self.assertIsNone(r.context["state_filter"], query)
            self.assertEqual(len(r.context["entities"]), 2, query)

    def test_clear_filters_url_keeps_the_columns_and_the_sorting(self):
        r = self.client.get(self.url("c=service&s=-service&q=x&f_service=y&state=1"))

        self.assertTrue(r.context["filters_active"])
        self.assertEqual(r.context["clear_filters_url"], f"{self.url()}?c=service&s=-service")

    def test_clear_filters_is_only_offered_while_a_filter_is_active(self):
        r = self.client.get(self.url())

        self.assertFalse(r.context["filters_active"])
        self.assertNotContains(r, "Clear filters")

    def test_filtering_keeps_the_selected_columns(self):
        r = self.client.get(self.url("c=service&f_service=ngin"))

        self.assertEqual(r.context["columns"], ["service"])
        # the columns are only in the url, so they have to be submitted with the filters
        self.assertContains(r, '<input type="hidden" class="entity-filter" name="c" value="service" />', html=True)

    def test_filter_matches_nothing_shows_a_filter_specific_message(self):
        r = self.client.get(self.url("f_service=nothinghere"))

        self.assertEqual(len(r.context["entities"]), 0)
        self.assertContains(r, "No entities match the filter.")


class EntityCreateViewTests(EntityTestCase):
    def test_get_ok(self):
        r = self.client.get(
            reverse("core:entity-create", kwargs={"project": self.project.pk, "entitytype": self.entitytype.name})
        )
        self.assertEqual(r.status_code, 200)

    def test_post_creates_entity_scoped_to_project_and_entitytype(self):
        r = self.client.post(
            reverse("core:entity-create", kwargs={"project": self.project.pk, "entitytype": self.entitytype.name}),
            {"data": '{"address": "1.2.3.4"}', "state": Entity.STATE_ENABLED},
        )
        self.assertEqual(r.status_code, 302)
        self.assertEqual(
            r.url, reverse("core:entity-list", kwargs={"project": self.project.pk, "entitytype": self.entitytype.name})
        )

        entity = Entity.objects.get(project=self.project, entitytype=self.entitytype)
        self.assertEqual(entity.data, {"address": "1.2.3.4"})

    def test_post_creating_enabled_entity_adds_event(self):
        self.client.post(
            reverse("core:entity-create", kwargs={"project": self.project.pk, "entitytype": self.entitytype.name}),
            {"data": '{"address": "1.2.3.4"}', "state": Entity.STATE_ENABLED},
        )

        entity = Entity.objects.get(project=self.project, entitytype=self.entitytype)
        self.assertEqual(Event.objects.filter(entity=entity).count(), 1)

    def test_post_creating_waiting_approval_entity_adds_no_event(self):
        self.client.post(
            reverse("core:entity-create", kwargs={"project": self.project.pk, "entitytype": self.entitytype.name}),
            {"data": '{"address": "1.2.3.4"}', "state": Entity.STATE_WAITING_APPROVAL},
        )

        entity = Entity.objects.get(project=self.project, entitytype=self.entitytype)
        self.assertEqual(Event.objects.filter(entity=entity).count(), 0)

    def test_post_data_not_matching_schema_is_rejected(self):
        r = self.client.post(
            reverse("core:entity-create", kwargs={"project": self.project.pk, "entitytype": self.entitytype.name}),
            {"data": '{"address": 12345}', "state": Entity.STATE_ENABLED},
        )
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Entity.objects.filter(project=self.project, entitytype=self.entitytype).exists())

    def test_get_data_widget_uses_the_fixed_entitytype_schema(self):
        r = self.client.get(
            reverse("core:entity-create", kwargs={"project": self.project.pk, "entitytype": self.entitytype.name})
        )
        # EntityForm adds the entitytype's name as "title" to the schema, so the editor shows it
        # (see EntityForm.__init__())
        self.assertEqual(r.context["form"].fields["data"].widget.schema, {**SCHEMA, "title": self.entitytype.name})

    def test_get_entitytype_is_not_a_form_field(self):
        r = self.client.get(
            reverse("core:entity-create", kwargs={"project": self.project.pk, "entitytype": self.entitytype.name})
        )
        self.assertNotIn("entitytype", r.context["form"].fields)


class EntityUpdateViewTests(EntityTestCase):
    def setUp(self):
        super().setUp()
        # created upfront, like self.entitytype in EntityTestCase.setUp(), so that
        # test_post_cannot_change_entitytype does not need to CREATE INDEX (via EntityType.save())
        # in the same transaction as an already-inserted Entity row
        self.other_entitytype = EntityType.objects.create(name="other", schema=SCHEMA, identifier_keys="address")
        self.entity = Entity.objects.create(
            entitytype=self.entitytype, project=self.project, data={"address": "1.1.1.1"}, state=Entity.STATE_ENABLED
        )

    def test_get_ok(self):
        r = self.client.get(reverse("core:entity-update", kwargs={"project": self.project.pk, "pk": self.entity.pk}))
        self.assertEqual(r.status_code, 200)

    def test_entity_of_other_project_is_404(self):
        r = self.client.get(
            reverse("core:entity-update", kwargs={"project": self.other_project.pk, "pk": self.entity.pk})
        )
        self.assertEqual(r.status_code, 404)

    def test_post_updates_data(self):
        r = self.client.post(
            reverse("core:entity-update", kwargs={"project": self.project.pk, "pk": self.entity.pk}),
            {
                "entitytype": self.entitytype.pk,
                "data": '{"address": "9.9.9.9"}',
                "state": Entity.STATE_ENABLED,
            },
        )
        self.assertEqual(r.status_code, 302)

        self.entity.refresh_from_db()
        self.assertEqual(self.entity.data, {"address": "9.9.9.9"})

    def test_post_transition_to_enabled_adds_event(self):
        self.entity.state = Entity.STATE_WAITING_APPROVAL
        self.entity.save()
        Event.objects.filter(entity=self.entity).delete()

        self.client.post(
            reverse("core:entity-update", kwargs={"project": self.project.pk, "pk": self.entity.pk}),
            {
                "entitytype": self.entitytype.pk,
                "data": '{"address": "1.1.1.1"}',
                "state": Entity.STATE_ENABLED,
            },
        )

        self.assertEqual(Event.objects.filter(entity=self.entity).count(), 1)

    def test_post_changing_identifier_key_data_adds_event(self):
        Event.objects.filter(entity=self.entity).delete()

        self.client.post(
            reverse("core:entity-update", kwargs={"project": self.project.pk, "pk": self.entity.pk}),
            {
                "entitytype": self.entitytype.pk,
                "data": '{"address": "9.9.9.9"}',
                "state": Entity.STATE_ENABLED,
            },
        )

        self.assertEqual(Event.objects.filter(entity=self.entity).count(), 1)

    def test_post_without_changing_identifier_key_data_adds_no_event(self):
        Event.objects.filter(entity=self.entity).delete()

        self.client.post(
            reverse("core:entity-update", kwargs={"project": self.project.pk, "pk": self.entity.pk}),
            {
                "entitytype": self.entitytype.pk,
                "data": '{"address": "1.1.1.1"}',
                "state": Entity.STATE_ENABLED,
            },
        )

        self.assertEqual(Event.objects.filter(entity=self.entity).count(), 0)

    def test_post_cannot_change_entitytype(self):
        self.client.post(
            reverse("core:entity-update", kwargs={"project": self.project.pk, "pk": self.entity.pk}),
            {
                "entitytype": self.other_entitytype.pk,
                "data": '{"address": "1.1.1.1"}',
                "state": Entity.STATE_ENABLED,
            },
        )

        self.entity.refresh_from_db()
        self.assertEqual(self.entity.entitytype, self.entitytype)

    def test_get_data_widget_uses_the_entitytype_schema(self):
        r = self.client.get(reverse("core:entity-update", kwargs={"project": self.project.pk, "pk": self.entity.pk}))
        # EntityForm adds the entitytype's name as "title" to the schema, so the editor shows it
        # (see EntityForm.__init__())
        self.assertEqual(r.context["form"].fields["data"].widget.schema, {**SCHEMA, "title": self.entitytype.name})

    def test_get_entitytype_is_not_a_form_field(self):
        r = self.client.get(reverse("core:entity-update", kwargs={"project": self.project.pk, "pk": self.entity.pk}))
        self.assertNotIn("entitytype", r.context["form"].fields)


class EntityStateChangeViewTests(EntityTestCase):
    def setUp(self):
        super().setUp()
        self.waiting_entity = Entity.objects.create(
            entitytype=self.entitytype,
            project=self.project,
            data={"address": "1.1.1.1"},
            state=Entity.STATE_WAITING_APPROVAL,
        )
        self.enabled_entity = Entity.objects.create(
            entitytype=self.entitytype,
            project=self.project,
            data={"address": "2.2.2.2"},
            state=Entity.STATE_ENABLED,
        )

    def _url(self, name, entity):
        return reverse(name, kwargs={"project": self.project.pk, "pk": entity.pk})

    def test_anonymous_redirected_to_login(self):
        self.client.logout()

        r = self.client.post(self._url("core:entity-approve", self.waiting_entity))
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login/", r.url)

    def test_approve_waiting_entity_enables_it_and_adds_event(self):
        r = self.client.post(self._url("core:entity-approve", self.waiting_entity))
        self.assertEqual(r.status_code, 302)

        self.waiting_entity.refresh_from_db()
        self.assertEqual(self.waiting_entity.state, Entity.STATE_ENABLED)
        self.assertEqual(Event.objects.filter(entity=self.waiting_entity).count(), 1)

    def test_approve_entity_not_waiting_for_approval_is_rejected(self):
        r = self.client.post(self._url("core:entity-approve", self.enabled_entity))
        self.assertEqual(r.status_code, 302)

        self.enabled_entity.refresh_from_db()
        self.assertEqual(self.enabled_entity.state, Entity.STATE_ENABLED)

        messages = list(get_messages(r.wsgi_request))
        self.assertTrue(any("not waiting for approval" in str(m) for m in messages))

    def test_decline_waiting_entity_disables_it_without_event(self):
        r = self.client.post(self._url("core:entity-decline", self.waiting_entity))
        self.assertEqual(r.status_code, 302)

        self.waiting_entity.refresh_from_db()
        self.assertEqual(self.waiting_entity.state, Entity.STATE_DISABLED)
        self.assertEqual(Event.objects.filter(entity=self.waiting_entity).count(), 0)

    def test_decline_entity_not_waiting_for_approval_is_rejected(self):
        r = self.client.post(self._url("core:entity-decline", self.enabled_entity))
        self.assertEqual(r.status_code, 302)

        self.enabled_entity.refresh_from_db()
        self.assertEqual(self.enabled_entity.state, Entity.STATE_ENABLED)

    def test_reprocess_enabled_entity_adds_another_event(self):
        self.assertEqual(Event.objects.filter(entity=self.enabled_entity).count(), 1)

        r = self.client.post(self._url("core:entity-reprocess", self.enabled_entity))
        self.assertEqual(r.status_code, 302)

        self.assertEqual(Event.objects.filter(entity=self.enabled_entity).count(), 2)

    def test_reprocess_non_enabled_entity_is_rejected(self):
        r = self.client.post(self._url("core:entity-reprocess", self.waiting_entity))
        self.assertEqual(r.status_code, 302)

        self.assertEqual(Event.objects.filter(entity=self.waiting_entity).count(), 0)

        messages = list(get_messages(r.wsgi_request))
        self.assertTrue(any("not enabled" in str(m) for m in messages))

    def test_redirects_to_list_without_querystring_by_default(self):
        r = self.client.post(self._url("core:entity-approve", self.waiting_entity))
        self.assertEqual(r.status_code, 302)
        self.assertEqual(
            r.url,
            reverse("core:entity-list", kwargs={"project": self.project.pk, "entitytype": self.entitytype.name}),
        )

    def test_redirect_preserves_filters_sort_and_columns(self):
        # the entity list's whole view state (shown columns, sorting, per column filters,
        # search, state filter) lives in its querystring - approving/declining/reprocessing an
        # entity must not reset it
        query_string = "c=address&s=-address&f_address=1.1&q=term&state=2"

        r = self.client.post(f"{self._url('core:entity-approve', self.waiting_entity)}?{query_string}")
        self.assertEqual(r.status_code, 302)

        redirect_path, _, redirect_query = r.url.partition("?")
        self.assertEqual(
            redirect_path,
            reverse("core:entity-list", kwargs={"project": self.project.pk, "entitytype": self.entitytype.name}),
        )
        self.assertEqual(QueryDict(redirect_query), QueryDict(query_string))

    def test_reprocess_redirect_also_preserves_querystring(self):
        query_string = "s=-address"

        r = self.client.post(f"{self._url('core:entity-reprocess', self.enabled_entity)}?{query_string}")
        self.assertEqual(r.status_code, 302)

        redirect_path, _, redirect_query = r.url.partition("?")
        self.assertEqual(
            redirect_path,
            reverse("core:entity-list", kwargs={"project": self.project.pk, "entitytype": self.entitytype.name}),
        )
        self.assertEqual(QueryDict(redirect_query), QueryDict(query_string))


class EntityDeleteViewTests(EntityTestCase):
    def test_get_shows_confirmation(self):
        entity = Entity.objects.create(
            entitytype=self.entitytype, project=self.project, data={"address": "1.1.1.1"}, state=Entity.STATE_ENABLED
        )

        r = self.client.get(reverse("core:entity-delete", kwargs={"project": self.project.pk, "pk": entity.pk}))
        self.assertEqual(r.status_code, 200)

    def test_post_deletes_entity(self):
        entity = Entity.objects.create(
            entitytype=self.entitytype, project=self.project, data={"address": "1.1.1.1"}, state=Entity.STATE_ENABLED
        )

        r = self.client.post(reverse("core:entity-delete", kwargs={"project": self.project.pk, "pk": entity.pk}))
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.url, reverse("core:entities", kwargs={"project": self.project.pk}))
        self.assertFalse(Entity.objects.filter(pk=entity.pk).exists())


class SchemaFormWidgetTests(TestCase):
    def test_render_includes_hidden_input_with_value(self):
        widget = JedisonWidget(schema=SCHEMA)
        html = widget.render("data", '{"address": "1.2.3.4"}', {"id": "id_data"})

        self.assertIn('name="data"', html)
        self.assertIn('value="{&quot;address&quot;: &quot;1.2.3.4&quot;}"', html)

    def test_render_includes_schema_as_json_script(self):
        widget = JedisonWidget(schema=SCHEMA)
        html = widget.render("data", None, {"id": "id_data"})

        self.assertIn('id="id_data-schema"', html)
        self.assertIn('"address"', html)
