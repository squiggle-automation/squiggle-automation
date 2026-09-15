import os
import tempfile
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.test import TestCase, override_settings
from django.urls import reverse

from squiggle_automation.testutils import random_password

from ..exceptions import ExecutionRetryError
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


class ExecutionRetryAllViewTests(ExecutionTestCase):
    def test_retries_all_failed_executions_in_project_only(self):
        other_project = Project.objects.create(name="project-2")

        Execution.objects.create(project=self.project, executor=self.executor, state=Execution.STATE_FAILED)
        Execution.objects.create(project=self.project, executor=self.executor, state=Execution.STATE_FAILED)
        Execution.objects.create(project=self.project, executor=self.executor, state=Execution.STATE_FINISHED)
        Execution.objects.create(project=other_project, executor=self.executor, state=Execution.STATE_FAILED)

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
