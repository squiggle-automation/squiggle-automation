import os
import tempfile
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from squiggle_automation.testutils import random_password

from ..exceptions import ExecutionAbortError, ExecutionRetryError
from ..models import (
    Container,
    Entity,
    EntityType,
    Execution,
    ExecutionLog,
    Executor,
    Project,
    WorkerProfile,
)
from ..tasks import run_executor as run_executor_task
from ..views import ExecutionDetailView

User = get_user_model()

ENTITY_SCHEMA = {"type": "object", "properties": {"address": {"type": "string"}}}


class ExecutionTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("plain", password=random_password())
        self.client.force_login(self.user)

        self.project = Project.objects.create(name="project-1")
        container = Container.objects.create(name="container", image="image")
        self.executor = Executor.objects.create(name="my-executor", container=container)


class ExecutionStateCategoryTests(SimpleTestCase):
    def test_every_state_is_in_exactly_one_category(self):
        # fails when a new state is added to STATE_CHOICES without putting it into a category
        categorized = [state for states in Execution.STATE_CATEGORIES.values() for state in states]
        self.assertCountEqual(categorized, Execution.STATE_CHOICES.keys())

    def test_every_category_has_a_label(self):
        self.assertEqual(Execution.STATE_CATEGORIES.keys(), Execution.STATE_CATEGORY_CHOICES.keys())


class ExecutionListViewTests(ExecutionTestCase):
    def test_anonymous_redirected_to_login(self):
        self.client.logout()

        r = self.client.get(reverse("core:executions", kwargs={"project": self.project.pk}))
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login/", r.url)

    def test_lists_only_executions_of_this_project_with_log_counts(self):
        other_project = Project.objects.create(name="project-2")
        Execution.objects.create(project=other_project, executor=self.executor)

        execution = Execution.objects.create(project=self.project, executor=self.executor)
        execution.add_log(ExecutionLog.LEVEL_ERROR, "boom")
        execution.add_log(ExecutionLog.LEVEL_ERROR, "boom again")
        execution.add_log(ExecutionLog.LEVEL_WARNING, "careful")
        execution.add_log(ExecutionLog.LEVEL_INFO, "fyi")

        r = self.client.get(reverse("core:executions", kwargs={"project": self.project.pk}))
        self.assertEqual(r.status_code, 200)

        executions = list(r.context["executions"])
        self.assertEqual(len(executions), 1)
        self.assertEqual(executions[0].error_count, 2)
        self.assertEqual(executions[0].warning_count, 1)
        self.assertEqual(executions[0].info_count, 1)
        self.assertEqual(executions[0].total_logs, 4)

    def test_shows_a_message_when_there_are_no_executions(self):
        r = self.client.get(reverse("core:executions", kwargs={"project": self.project.pk}))

        self.assertContains(r, "No executions yet.")

    def test_htmx_request_renders_only_the_list(self):
        Execution.objects.create(project=self.project, executor=self.executor)

        r = self.client.get(
            reverse("core:executions", kwargs={"project": self.project.pk}), headers={"hx-request": "true"}
        )

        self.assertEqual(r.status_code, 200)
        self.assertTemplateUsed(r, "core/execution_list_content.html")
        self.assertTemplateNotUsed(r, "core/execution_list.html")
        self.assertNotContains(r, "<aside")
        # the button is part of the swapped content, otherwise it would not follow the filters
        self.assertContains(r, "Retry all failed")

    def test_history_restore_renders_the_full_page(self):
        r = self.client.get(
            reverse("core:executions", kwargs={"project": self.project.pk}),
            headers={"hx-request": "true", "hx-history-restore-request": "true"},
        )

        self.assertEqual(r.status_code, 200)
        self.assertTemplateUsed(r, "core/execution_list.html")
        self.assertContains(r, "<aside")


class ExecutionListSortTests(ExecutionTestCase):
    """Sorting of the execution list, see ExecutionListView.get_sort()."""

    def setUp(self):
        super().setUp()

        container = self.executor.container
        self.executor_a = Executor.objects.create(name="a-executor", container=container)
        self.executor_z = Executor.objects.create(name="z-executor", container=container)

        # created in this order, so created_at (and pk) ascend in it. the executor names and the
        # states sort differently than that, so a mix-up of the orderings cannot pass unnoticed
        self.first = Execution.objects.create(
            project=self.project, executor=self.executor_z, state=Execution.STATE_QUEUED
        )
        self.second = Execution.objects.create(
            project=self.project, executor=self.executor_a, state=Execution.STATE_FAILED
        )
        self.third = Execution.objects.create(
            project=self.project, executor=self.executor, state=Execution.STATE_FINISHED
        )

    def url(self, query=""):
        url = reverse("core:executions", kwargs={"project": self.project.pk})

        return f"{url}?{query}" if query else url

    def test_default_sorting_is_newest_first(self):
        r = self.client.get(self.url())

        self.assertEqual(r.context["sort_key"], "created_at")
        self.assertTrue(r.context["sort_descending"])
        self.assertEqual(list(r.context["executions"]), [self.third, self.second, self.first])

    def test_sort_ascending_by_executor_name(self):
        r = self.client.get(self.url("s=executor"))

        self.assertEqual(r.context["sort_key"], "executor")
        self.assertFalse(r.context["sort_descending"])
        # a-executor, my-executor, z-executor
        self.assertEqual(list(r.context["executions"]), [self.second, self.third, self.first])

    def test_sort_descending_by_state(self):
        r = self.client.get(self.url("s=-state"))

        # failed (7), finished (6), queued (3)
        self.assertEqual(list(r.context["executions"]), [self.second, self.third, self.first])

    def test_sort_ascending_by_created_at(self):
        r = self.client.get(self.url("s=created_at"))

        self.assertEqual(list(r.context["executions"]), [self.first, self.second, self.third])

    def test_unknown_sort_column_falls_back_to_the_default(self):
        for query in ["s=nope", "s=-nope", "s=executor__name", "s="]:
            r = self.client.get(self.url(query))

            self.assertEqual(r.context["sort_key"], "created_at", query)
            self.assertTrue(r.context["sort_descending"], query)
            self.assertEqual(list(r.context["executions"]), [self.third, self.second, self.first], query)

    def test_rows_with_equal_sort_values_are_newest_first(self):
        Execution.objects.filter(pk__in=[self.first.pk, self.second.pk, self.third.pk]).update(
            state=Execution.STATE_FAILED
        )

        r = self.client.get(self.url("s=state"))

        self.assertEqual(list(r.context["executions"]), [self.third, self.second, self.first])

    def test_header_links_sort_ascending_and_flip_to_descending(self):
        r = self.client.get(self.url())

        headers = r.context["sort_headers"]
        self.assertEqual(set(headers), {"executor", "state", "created_at"})
        # the default sorting shows up on its column, and clicking it flips the direction
        self.assertTrue(headers["created_at"]["sorted"])
        self.assertTrue(headers["created_at"]["descending"])
        self.assertEqual(headers["created_at"]["url"], f"{self.url()}?s=created_at")
        self.assertFalse(headers["executor"]["sorted"])
        self.assertEqual(headers["executor"]["url"], f"{self.url()}?s=executor")

        # following it sorts ascending, and offers descending next
        r = self.client.get(headers["executor"]["url"])
        header = r.context["sort_headers"]["executor"]
        self.assertTrue(header["sorted"])
        self.assertFalse(header["descending"])
        self.assertEqual(header["url"], f"{self.url()}?s=-executor")
        self.assertContains(r, 'aria-sort="ascending"')

        r = self.client.get(header["url"])
        header = r.context["sort_headers"]["executor"]
        self.assertTrue(header["descending"])
        self.assertEqual(header["url"], f"{self.url()}?s=executor")
        self.assertContains(r, 'aria-sort="descending"')

    def test_sorting_keeps_the_filters_and_drops_the_page(self):
        r = self.client.get(self.url("q=exec&state=7&page=1"))

        self.assertEqual(r.context["sort_headers"]["state"]["url"], f"{self.url()}?q=exec&state=7&s=state")

    def test_sorting_is_sent_along_with_the_filters(self):
        r = self.client.get(self.url("s=-executor"))

        # the hidden input that hx-include picks up when a filter changes
        self.assertContains(r, '<input type="hidden" class="execution-filter" name="s" value="-executor">', html=True)


class ExecutionListFilterTests(ExecutionTestCase):
    """Searching and filtering of the execution list, see ExecutionListView.get_queryset()."""

    def setUp(self):
        super().setUp()

        self.nmap = Executor.objects.create(name="nmap", container=self.executor.container)

        self.failed = Execution.objects.create(
            project=self.project, executor=self.executor, state=Execution.STATE_FAILED
        )
        self.finished = Execution.objects.create(
            project=self.project, executor=self.nmap, state=Execution.STATE_FINISHED
        )

    def url(self, query=""):
        url = reverse("core:executions", kwargs={"project": self.project.pk})

        return f"{url}?{query}" if query else url

    def test_search_matches_a_substring_of_the_executor_name(self):
        r = self.client.get(self.url("q=NMA"))

        self.assertEqual(r.context["search_term"], "NMA")
        self.assertEqual(list(r.context["executions"]), [self.finished])

    def test_search_for_a_number_also_matches_the_execution_id(self):
        r = self.client.get(self.url(f"q={self.failed.pk}"))

        self.assertIn(self.failed, list(r.context["executions"]))

    def test_search_for_a_number_also_matches_the_executor_name(self):
        executor = Executor.objects.create(name="executor-12345678", container=self.executor.container)
        execution = Execution.objects.create(project=self.project, executor=executor)

        r = self.client.get(self.url("q=12345678"))

        self.assertEqual(list(r.context["executions"]), [execution])

    def test_search_for_an_id_out_of_range_matches_nothing(self):
        for term in ["99999999999999999999999999", "²"]:
            r = self.client.get(self.url(f"q={term}"))

            self.assertEqual(r.status_code, 200, term)
            self.assertEqual(list(r.context["executions"]), [], term)

    def test_search_does_not_find_executions_of_other_projects(self):
        other_project = Project.objects.create(name="project-2")
        other = Execution.objects.create(project=other_project, executor=self.nmap)

        r = self.client.get(self.url(f"q={other.pk}"))
        self.assertNotIn(other, list(r.context["executions"]))

        r = self.client.get(self.url("q=nmap"))
        self.assertEqual(list(r.context["executions"]), [self.finished])

    def test_state_category_can_be_filtered(self):
        r = self.client.get(self.url("state=failed"))

        self.assertEqual(r.context["state_filter"], Execution.STATE_CATEGORY_FAILED)
        self.assertEqual(list(r.context["executions"]), [self.failed])
        self.assertContains(r, '<option value="failed" selected>', html=False)

    def test_state_category_filter_matches_all_states_of_the_category(self):
        running = Execution.objects.create(project=self.project, executor=self.executor, state=Execution.STATE_RUNNING)
        processing = Execution.objects.create(
            project=self.project, executor=self.executor, state=Execution.STATE_PROCESSING_RESULTS
        )
        aborted = Execution.objects.create(project=self.project, executor=self.executor, state=Execution.STATE_ABORTED)

        r = self.client.get(self.url("state=running"))
        self.assertCountEqual(r.context["executions"], [running, processing])

        r = self.client.get(self.url("state=done"))
        self.assertCountEqual(r.context["executions"], [self.finished, aborted])

    def test_every_state_category_is_offered(self):
        r = self.client.get(self.url())

        for category in Execution.STATE_CATEGORY_CHOICES:
            self.assertContains(r, f'<option value="{category}"', html=False)

    def test_invalid_state_is_ignored(self):
        for query in ["state=nope", f"state={Execution.STATE_FAILED}", "state="]:
            r = self.client.get(self.url(query))

            self.assertIsNone(r.context["state_filter"], query)
            self.assertEqual(len(r.context["executions"]), 2, query)

    def test_search_and_state_are_combined(self):
        r = self.client.get(self.url("q=nmap&state=failed"))

        self.assertEqual(list(r.context["executions"]), [])
        self.assertContains(r, "No executions match the filter.")

    def test_clear_filters_url_keeps_the_sorting(self):
        r = self.client.get(self.url("s=-state&q=x&state=failed&page=1"))

        self.assertTrue(r.context["filters_active"])
        self.assertEqual(r.context["clear_filters_url"], f"{self.url()}?s=-state")

    def test_clear_filters_is_only_offered_while_a_filter_is_active(self):
        r = self.client.get(self.url("q="))

        self.assertFalse(r.context["filters_active"])
        self.assertNotContains(r, "Clear filters")

    def test_retry_all_failed_is_enabled_without_a_filter(self):
        r = self.client.get(self.url("s=state"))

        self.assertNotContains(r, "Clear the filters to use it.")
        self.assertNotContains(r, "disabled")

    def test_retry_all_failed_is_disabled_while_a_filter_is_active(self):
        for query in ["q=nmap", "state=failed"]:
            r = self.client.get(self.url(query))

            self.assertContains(r, "Clear the filters to use it.", msg_prefix=query)
            self.assertContains(
                r,
                '<button type="submit" class="btn btn-sm btn-outline-primary" disabled>',
                msg_prefix=query,
            )


class ExecutionDetailViewTests(ExecutionTestCase):
    def test_execution_of_other_project_is_404(self):
        other_project = Project.objects.create(name="project-2")
        execution = Execution.objects.create(project=other_project, executor=self.executor)

        r = self.client.get(reverse("core:execution-details", kwargs={"project": self.project.pk, "pk": execution.pk}))
        self.assertEqual(r.status_code, 404)

    def test_shows_logs_and_applied_config(self):
        execution = Execution.objects.create(
            project=self.project, executor=self.executor, applied_config={"option": "value"}
        )
        execution.add_log(ExecutionLog.LEVEL_INFO, "hello")

        r = self.client.get(reverse("core:execution-details", kwargs={"project": self.project.pk, "pk": execution.pk}))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(list(r.context["logs"]), list(ExecutionLog.objects.filter(execution=execution)))
        self.assertContains(r, "hello")

    def test_shows_no_artifacts_message_without_output_directory(self):
        execution = Execution.objects.create(project=self.project, executor=self.executor)

        r = self.client.get(reverse("core:execution-details", kwargs={"project": self.project.pk, "pk": execution.pk}))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context["artifacts"], [])
        self.assertFalse(r.context["artifacts_limit_reached"])
        self.assertContains(r, "No artifacts.")

    def test_shows_artifact_files_sorted_by_name(self):
        with tempfile.TemporaryDirectory() as artifacts_dir:
            execution = Execution.objects.create(
                project=self.project, executor=self.executor, output_directory_name="run-1"
            )
            output_dir = os.path.join(artifacts_dir, f"project_{self.project.id}", "run-1")
            os.makedirs(output_dir)
            for name in ("nmap.stdout", "a-report.json"):
                open(os.path.join(output_dir, name), "w").close()

            with override_settings(ARTIFACTS_DIR=artifacts_dir):
                r = self.client.get(
                    reverse("core:execution-details", kwargs={"project": self.project.pk, "pk": execution.pk})
                )

        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context["artifacts"], ["a-report.json", "nmap.stdout"])
        self.assertFalse(r.context["artifacts_limit_reached"])
        self.assertContains(r, "a-report.json")
        self.assertContains(r, "nmap.stdout")
        self.assertNotContains(r, "More artifacts are available but not shown here.")
        self.assertContains(
            r,
            reverse(
                "core:execution-artifact-download",
                kwargs={"project": self.project.pk, "pk": execution.pk, "filename": "a-report.json"},
            ),
        )

    def test_shows_hint_when_more_artifacts_than_the_display_limit_exist(self):
        with tempfile.TemporaryDirectory() as artifacts_dir:
            execution = Execution.objects.create(
                project=self.project, executor=self.executor, output_directory_name="run-1"
            )
            output_dir = os.path.join(artifacts_dir, f"project_{self.project.id}", "run-1")
            os.makedirs(output_dir)
            for i in range(ExecutionDetailView.artifacts_limit + 1):
                open(os.path.join(output_dir, f"file-{i:02d}.txt"), "w").close()

            with override_settings(ARTIFACTS_DIR=artifacts_dir):
                r = self.client.get(
                    reverse("core:execution-details", kwargs={"project": self.project.pk, "pk": execution.pk})
                )

        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.context["artifacts"]), ExecutionDetailView.artifacts_limit)
        self.assertTrue(r.context["artifacts_limit_reached"])
        self.assertContains(r, "More artifacts are available but not shown here.")

    def test_shows_link_to_input_entities_view_without_loading_entities(self):
        execution = Execution.objects.create(project=self.project, executor=self.executor)

        r = self.client.get(reverse("core:execution-details", kwargs={"project": self.project.pk, "pk": execution.pk}))
        self.assertEqual(r.status_code, 200)
        # the whole point is that the detail view does not load the input entities itself
        self.assertNotIn("entities", r.context)
        self.assertContains(
            r,
            reverse("core:execution-input-entities", kwargs={"project": self.project.pk, "pk": execution.pk}),
        )


class ExecutionInputEntitiesViewTests(ExecutionTestCase):
    def setUp(self):
        super().setUp()
        self.entitytype = EntityType.objects.create(name="host", schema=ENTITY_SCHEMA, identifier_keys="address")

    def _url(self, execution):
        return reverse("core:execution-input-entities", kwargs={"project": self.project.pk, "pk": execution.pk})

    def test_anonymous_redirected_to_login(self):
        execution = Execution.objects.create(project=self.project, executor=self.executor)
        self.client.logout()

        r = self.client.get(self._url(execution))
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login/", r.url)

    def test_execution_of_other_project_is_404(self):
        other_project = Project.objects.create(name="project-2")
        execution = Execution.objects.create(project=other_project, executor=self.executor)

        r = self.client.get(self._url(execution))
        self.assertEqual(r.status_code, 404)

    def test_shows_no_input_entities_message_when_empty(self):
        execution = Execution.objects.create(project=self.project, executor=self.executor)

        r = self.client.get(self._url(execution))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(list(r.context["entities"]), [])
        self.assertContains(r, "No input entities.")

    def test_shows_only_entities_linked_to_this_execution(self):
        execution = Execution.objects.create(project=self.project, executor=self.executor)
        other_execution = Execution.objects.create(project=self.project, executor=self.executor)

        entity = Entity.objects.create(
            entitytype=self.entitytype, project=self.project, data={"address": "1.1.1.1"}, state=Entity.STATE_ENABLED
        )
        other_entity = Entity.objects.create(
            entitytype=self.entitytype, project=self.project, data={"address": "2.2.2.2"}, state=Entity.STATE_ENABLED
        )
        execution.entities.add(entity)
        other_execution.entities.add(other_entity)

        r = self.client.get(self._url(execution))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(list(r.context["entities"]), [entity])
        self.assertContains(r, "1.1.1.1")
        self.assertNotContains(r, "2.2.2.2")


class ExecutionArtifactDownloadViewTests(ExecutionTestCase):
    def _download_url(self, execution, filename):
        return reverse(
            "core:execution-artifact-download",
            kwargs={"project": self.project.pk, "pk": execution.pk, "filename": filename},
        )

    def test_anonymous_redirected_to_login(self):
        execution = Execution.objects.create(
            project=self.project, executor=self.executor, output_directory_name="run-1"
        )
        self.client.logout()

        r = self.client.get(self._download_url(execution, "report.json"))
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login/", r.url)

    def test_downloads_artifact_file(self):
        with tempfile.TemporaryDirectory() as artifacts_dir:
            execution = Execution.objects.create(
                project=self.project, executor=self.executor, output_directory_name="run-1"
            )
            output_dir = os.path.join(artifacts_dir, f"project_{self.project.id}", "run-1")
            os.makedirs(output_dir)
            with open(os.path.join(output_dir, "report.json"), "w") as f:
                f.write('{"result": "ok"}')

            with override_settings(ARTIFACTS_DIR=artifacts_dir):
                r = self.client.get(self._download_url(execution, "report.json"))

        self.assertEqual(r.status_code, 200)
        self.assertEqual(b"".join(r.streaming_content), b'{"result": "ok"}')
        self.assertIn('filename="report.json"', r.headers["Content-Disposition"])
        self.assertEqual(r.headers["Content-Disposition"].split(";")[0], "attachment")

    def test_unknown_filename_is_404(self):
        with tempfile.TemporaryDirectory() as artifacts_dir:
            execution = Execution.objects.create(
                project=self.project, executor=self.executor, output_directory_name="run-1"
            )
            output_dir = os.path.join(artifacts_dir, f"project_{self.project.id}", "run-1")
            os.makedirs(output_dir)
            open(os.path.join(output_dir, "report.json"), "w").close()

            with override_settings(ARTIFACTS_DIR=artifacts_dir):
                r = self.client.get(self._download_url(execution, "does-not-exist.json"))

        self.assertEqual(r.status_code, 404)

    def test_path_traversal_attempt_is_404(self):
        with tempfile.TemporaryDirectory() as artifacts_dir:
            execution = Execution.objects.create(
                project=self.project, executor=self.executor, output_directory_name="run-1"
            )
            output_dir = os.path.join(artifacts_dir, f"project_{self.project.id}", "run-1")
            os.makedirs(output_dir)
            open(os.path.join(output_dir, "report.json"), "w").close()

            # a file that does exist, just one directory up from the artifact directory
            with open(os.path.join(artifacts_dir, "secret.txt"), "w") as f:
                f.write("secret")

            with override_settings(ARTIFACTS_DIR=artifacts_dir):
                r = self.client.get(self._download_url(execution, ".."))

        self.assertEqual(r.status_code, 404)

    def test_execution_of_other_project_is_404(self):
        other_project = Project.objects.create(name="project-2")
        execution = Execution.objects.create(project=other_project, executor=self.executor)

        r = self.client.get(self._download_url(execution, "report.json"))
        self.assertEqual(r.status_code, 404)


class ExecutionRetryViewTests(ExecutionTestCase):
    def test_retry_aborted_execution_calls_schedule(self):
        execution = Execution.objects.create(
            project=self.project, executor=self.executor, state=Execution.STATE_ABORTED
        )

        with patch("core.models.execution.Execution.schedule") as mock_schedule:
            self.client.post(reverse("core:execution-retry", kwargs={"project": self.project.pk, "pk": execution.pk}))

        mock_schedule.assert_called_once()

    def test_retry_failed_execution_calls_schedule(self):
        execution = Execution.objects.create(project=self.project, executor=self.executor, state=Execution.STATE_FAILED)

        with patch("core.models.execution.Execution.schedule") as mock_schedule:
            r = self.client.post(
                reverse("core:execution-retry", kwargs={"project": self.project.pk, "pk": execution.pk})
            )

        self.assertEqual(r.status_code, 302)
        self.assertEqual(
            r.url, reverse("core:execution-details", kwargs={"project": self.project.pk, "pk": execution.pk})
        )
        mock_schedule.assert_called_once()

    def test_retry_running_execution_shows_error_and_does_not_schedule(self):
        execution = Execution.objects.create(
            project=self.project, executor=self.executor, state=Execution.STATE_RUNNING
        )

        with patch("core.models.execution.Execution.schedule") as mock_schedule:
            r = self.client.post(
                reverse("core:execution-retry", kwargs={"project": self.project.pk, "pk": execution.pk})
            )

        self.assertEqual(r.status_code, 302)
        mock_schedule.assert_not_called()

        messages = list(get_messages(r.wsgi_request))
        self.assertTrue(any("cannot be retried" in str(m) for m in messages))


class ExecutionAbortViewTests(ExecutionTestCase):
    def _post(self, execution):
        return self.client.post(
            reverse("core:execution-abort", kwargs={"project": self.project.pk, "pk": execution.pk})
        )

    def test_abort_queued_and_failed_execution(self):
        for state in (Execution.STATE_QUEUED, Execution.STATE_FAILED):
            execution = Execution.objects.create(project=self.project, executor=self.executor, state=state)
            r = self._post(execution)
            self.assertEqual(r.status_code, 302)
            execution.refresh_from_db()
            self.assertEqual(execution.state, Execution.STATE_ABORTED)

    def test_abort_running_execution_shows_error(self):
        execution = Execution.objects.create(
            project=self.project, executor=self.executor, state=Execution.STATE_RUNNING
        )
        r = self._post(execution)
        execution.refresh_from_db()
        self.assertEqual(execution.state, Execution.STATE_RUNNING)
        messages = list(get_messages(r.wsgi_request))
        self.assertTrue(any("cannot be aborted" in str(m) for m in messages))

    def test_abort_other_project_returns_404(self):
        other_project = Project.objects.create(name="project-2")
        execution = Execution.objects.create(
            project=other_project, executor=self.executor, state=Execution.STATE_FAILED
        )
        r = self.client.post(reverse("core:execution-abort", kwargs={"project": self.project.pk, "pk": execution.pk}))
        self.assertEqual(r.status_code, 404)


class ExecutionRetryAllViewTests(ExecutionTestCase):
    def test_retries_all_failed_executions_in_project_only(self):
        other_project = Project.objects.create(name="project-2")

        Execution.objects.create(project=self.project, executor=self.executor, state=Execution.STATE_FAILED)
        Execution.objects.create(project=self.project, executor=self.executor, state=Execution.STATE_FAILED)
        Execution.objects.create(project=self.project, executor=self.executor, state=Execution.STATE_FINISHED)
        Execution.objects.create(project=other_project, executor=self.executor, state=Execution.STATE_FAILED)
        Execution.objects.create(project=self.project, executor=self.executor, state=Execution.STATE_ABORTED)

        with patch("core.models.execution.Execution.schedule") as mock_schedule:
            r = self.client.post(reverse("core:execution-retry-all", kwargs={"project": self.project.pk}))

        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.url, reverse("core:executions", kwargs={"project": self.project.pk}))
        self.assertEqual(mock_schedule.call_count, 2)

    def test_retry_error_for_individual_execution_is_ignored(self):
        Execution.objects.create(project=self.project, executor=self.executor, state=Execution.STATE_FAILED)
        Execution.objects.create(project=self.project, executor=self.executor, state=Execution.STATE_FAILED)

        with patch("core.models.execution.Execution.schedule", side_effect=ExecutionRetryError):
            r = self.client.post(reverse("core:execution-retry-all", kwargs={"project": self.project.pk}))

        # even though retry() raises for every execution, the view does not fail
        self.assertEqual(r.status_code, 302)


class ExecutionModelTests(TestCase):
    def setUp(self):
        self.project = Project.objects.create(name="project-1")
        container = Container.objects.create(name="container", image="image")
        self.executor = Executor.objects.create(name="my-executor", container=container)

    def test_retry_raises_for_running_execution(self):
        execution = Execution.objects.create(
            project=self.project, executor=self.executor, state=Execution.STATE_RUNNING
        )
        with self.assertRaises(ExecutionRetryError):
            execution.retry()

    def test_retry_schedules_for_finished_execution(self):
        execution = Execution.objects.create(
            project=self.project, executor=self.executor, state=Execution.STATE_FINISHED
        )
        with patch("core.models.execution.Execution.schedule") as mock_schedule:
            execution.retry()
        mock_schedule.assert_called_once()

    def test_retry_calls_schedule_for_failed_execution(self):
        execution = Execution.objects.create(project=self.project, executor=self.executor, state=Execution.STATE_FAILED)

        with patch("core.models.execution.Execution.schedule") as mock_schedule:
            execution.retry()

        mock_schedule.assert_called_once()

    def test_abort_raises_for_running_execution(self):
        execution = Execution.objects.create(
            project=self.project, executor=self.executor, state=Execution.STATE_RUNNING
        )
        with self.assertRaises(ExecutionAbortError):
            execution.abort()

    def test_retry_calls_schedule_for_aborted_execution(self):
        execution = Execution.objects.create(
            project=self.project, executor=self.executor, state=Execution.STATE_ABORTED
        )
        with patch("core.models.execution.Execution.schedule") as mock_schedule:
            execution.retry()
        mock_schedule.assert_called_once()

    def test_run_executor_task_skips_aborted_execution(self):
        execution = Execution.objects.create(
            project=self.project, executor=self.executor, state=Execution.STATE_ABORTED
        )
        run_executor_task(execution.id)
        execution.refresh_from_db()
        self.assertEqual(execution.state, Execution.STATE_ABORTED)
        self.assertEqual(execution.get_log().count(), 0)

    def test_schedule_fails_without_any_worker_profile_configured(self):
        execution = Execution.objects.create(project=self.project, executor=self.executor)

        with patch.object(run_executor_task, "apply_async") as mock_apply_async:
            execution.schedule()

        mock_apply_async.assert_not_called()
        execution.refresh_from_db()
        self.assertEqual(execution.state, Execution.STATE_FAILED)

    def test_schedule_queues_task_on_default_worker_profile_queue(self):
        WorkerProfile.objects.create(name="worker-queue")  # becomes default automatically
        execution = Execution.objects.create(project=self.project, executor=self.executor)

        # the actual apply_async() dispatch is deferred until the transaction commits (see
        # Execution.schedule()), so it must be captured explicitly here
        with patch.object(run_executor_task, "apply_async") as mock_apply_async:
            with self.captureOnCommitCallbacks(execute=True):
                execution.schedule()

        mock_apply_async.assert_called_once_with((execution.id,), queue="worker-queue")
        execution.refresh_from_db()
        self.assertEqual(execution.state, Execution.STATE_QUEUED)

    def test_artifact_files_is_empty_without_output_directory(self):
        execution = Execution.objects.create(project=self.project, executor=self.executor)
        self.assertEqual(execution.artifact_files(), ([], False))

    def test_artifact_files_is_empty_when_directory_does_not_exist_on_disk(self):
        execution = Execution.objects.create(
            project=self.project, executor=self.executor, output_directory_name="does-not-exist"
        )
        self.assertEqual(execution.artifact_files(), ([], False))

    def test_artifact_files_lists_files_in_artifact_directory_sorted_by_name(self):
        with tempfile.TemporaryDirectory() as artifacts_dir:
            execution = Execution.objects.create(
                project=self.project, executor=self.executor, output_directory_name="run-1"
            )
            output_dir = os.path.join(artifacts_dir, f"project_{self.project.id}", "run-1")
            os.makedirs(output_dir)
            for name in ("b.txt", "a.txt"):
                open(os.path.join(output_dir, name), "w").close()

            with override_settings(ARTIFACTS_DIR=artifacts_dir):
                self.assertEqual(execution.artifact_files(), (["a.txt", "b.txt"], False))

    def test_artifact_files_respects_limit(self):
        with tempfile.TemporaryDirectory() as artifacts_dir:
            execution = Execution.objects.create(
                project=self.project, executor=self.executor, output_directory_name="run-1"
            )
            output_dir = os.path.join(artifacts_dir, f"project_{self.project.id}", "run-1")
            os.makedirs(output_dir)
            for name in ("a.txt", "b.txt", "c.txt"):
                open(os.path.join(output_dir, name), "w").close()

            with override_settings(ARTIFACTS_DIR=artifacts_dir):
                self.assertEqual(execution.artifact_files(limit=2), (["a.txt", "b.txt"], True))
                self.assertEqual(execution.artifact_files(limit=3), (["a.txt", "b.txt", "c.txt"], False))
                self.assertEqual(execution.artifact_files(limit=4), (["a.txt", "b.txt", "c.txt"], False))
