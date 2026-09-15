import os
import tempfile
from datetime import datetime, timedelta

from django.conf import settings
from django.db import models, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from ..exceptions import ExecutionInputError, ExecutionRetryError
from .entity import Entity
from .executionlog import ExecutionLog
from .executor import Executor
from .project import Project


class Execution(models.Model):
    class Meta:
        ordering = ["-created_at"]

    STATE_FILLING = 1
    STATE_MANUAL = 2
    STATE_QUEUED = 3
    STATE_RUNNING = 4
    STATE_PROCESSING_RESULTS = 5
    STATE_FINISHED = 6
    STATE_FAILED = 7

    STATE_CHOICES = {
        STATE_FILLING: _("Filling with entities"),
        STATE_MANUAL: _("Manually added"),
        STATE_QUEUED: _("Queued"),
        STATE_RUNNING: _("Running"),
        STATE_PROCESSING_RESULTS: _("Processing results"),
        STATE_FINISHED: _("Finished"),
        STATE_FAILED: _("Execution failed"),
    }

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        verbose_name=_("Project"),
    )

    executor = models.ForeignKey(
        Executor,
        on_delete=models.CASCADE,
        verbose_name=_("Executor"),
    )

    state = models.IntegerField(
        choices=STATE_CHOICES,
        default=STATE_MANUAL,
        verbose_name=_("State"),
    )

    entities = models.ManyToManyField(
        Entity,
        verbose_name=_("Entities"),
    )
    # TODO: validate that entities.project is always project

    output_directory_name = models.CharField(
        blank=True,
        null=False,
        verbose_name=_("Directory name for artifacts and temporary files (relative path, just the directory name)"),
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    scheduled_at = models.DateTimeField(
        null=True,
    )

    applied_config = models.JSONField(
        blank=True,
        null=True,
        verbose_name=_("Applied configuration"),
        help_text=_("Config values used for this execution. Sensitive values are masked."),
    )

    def __str__(self):
        return f"{self.executor.name}, {self.created_at}"

    def update_state(self, new_state):
        self.state = new_state
        self.save()

        new_state_name = Execution.STATE_CHOICES.get(new_state, new_state)
        self.add_log(ExecutionLog.LEVEL_SCHEDULER, f'state changed to "{new_state_name}"')

    def add_log(self, level, message):
        ExecutionLog.objects.create(execution=self, level=level, message=message)

    def get_log(self, level=None):
        if level:
            return ExecutionLog.objects.filter(execution=self, level=level)
        else:
            return ExecutionLog.objects.filter(execution=self)

    def schedule(self):
        from ..tasks import run_executor

        # get the queue name
        queue = self.queue_name
        if queue is None:
            self.add_log(ExecutionLog.LEVEL_ERROR, "no default worker profile configured")
            self.update_state(Execution.STATE_FAILED)
            return

        # update state to queued
        self.scheduled_at = timezone.now()
        self.update_state(Execution.STATE_QUEUED)  # this calls save

        # queue the execution once the current transaction (if any) commits, so a worker can
        # never pick this up before the state change above is visible to other connections -
        # e.g. _fill_executions() calls schedule() from within a transaction.atomic() block
        transaction.on_commit(lambda: run_executor.apply_async((self.id,), queue=queue))

    def retry(self):
        if self.failed or self.finished:
            self.schedule()
        else:
            raise ExecutionRetryError

    def get_used_input_entitytypes(self):
        """
        Get entitytypes that are actually used in the input.

        Raises ExecutionInputError if the entitytype of an input entity is not supportd by the executor.
        """
        entitytypes_provided = set(self.entities.order_by("entitytype").values_list("entitytype", flat=True).distinct())
        entitytypes_supported = set(self.executor.input.values_list("pk", flat=True))

        # remove all supported types from the provided. if something is left, we have a problem
        if entitytypes_provided.difference(entitytypes_supported) != set():
            raise ExecutionInputError("entities provided that do not match a supported input type")

        return entitytypes_provided

    def create_work_directories(self):
        """
        Create folders for this execution:

        ARTIFACTS_DIR/tool_id_timestamp_random
        TMP_DIR/tool_id_timestamp_random/tmp
        TMP_DIR/tool_id_timestamp_random/input
        TMP_DIR/tool_id_timestamp_random/output

        Returns list: dir_artifacts, dir_input, dir_output, dir_tmp
        """
        # make sure that project directories exist
        project_dir_artifacts = os.path.join(settings.ARTIFACTS_DIR, f"project_{self.project.id}")
        project_dir_temp = os.path.join(settings.TMP_DIR, f"project_{self.project.id}")

        os.makedirs(project_dir_artifacts, exist_ok=True)
        os.makedirs(project_dir_temp, exist_ok=True)

        # create new artifacts directory
        # output_directory_name is then the generated folder name including the random part
        # this is reused to create the temporary directorys so that we have the same random part in it
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        prefix = f"{self.executor.name}_{self.id}_{timestamp}_"
        work_dir_artifacts = tempfile.mkdtemp(dir=project_dir_artifacts, prefix=prefix)
        self.output_directory_name = os.path.basename(work_dir_artifacts)

        # create new input, output, temp directories
        tmp_base_dir = os.path.join(project_dir_temp, self.output_directory_name)
        work_dir_input = os.path.join(tmp_base_dir, "input")
        work_dir_output = os.path.join(tmp_base_dir, "output")
        work_dir_tmp = os.path.join(tmp_base_dir, "tmp")

        os.makedirs(work_dir_input)
        os.makedirs(work_dir_output)
        os.makedirs(work_dir_tmp)

        return work_dir_artifacts, work_dir_input, work_dir_output, work_dir_tmp

    @property
    def artifact_directory(self):
        if self.output_directory_name:
            return os.path.join(settings.ARTIFACTS_DIR, f"project_{self.project.id}", self.output_directory_name)
        return None

    def artifact_files(self, limit=None):
        """
        Names of the files in the artifact directory, sorted.

        If limit is provided, only that number of files are returned.

        Return a tuple (files, limit_reached)
        """
        directory = self.artifact_directory
        if not directory or not os.path.isdir(directory):
            return [], False

        files = sorted(os.listdir(directory))
        if limit is not None and len(files) > limit:
            return files[:limit], True
        return files, False

    @property
    def tmp_directory(self):
        if self.output_directory_name:
            return os.path.join(settings.TMP_DIR, f"project_{self.project.id}", self.output_directory_name)
        return None

    @property
    def max_entities_missing(self):
        """Number of entities that are missing until max number is reached."""
        diff = self.executor.max_entities - self.entities.count()
        return max(diff, 0)

    @property
    def max_entities_timeout_reached(self):
        timeout = self.executor.max_entities_timeout
        if timeout == 0:
            return True
        return self.created_at + timedelta(minutes=timeout) <= timezone.now()

    @property
    def queue_name(self):
        from .workerprofile import WorkerProfile

        # is a worker profile configured?
        if self.executor.workerprofile:
            return self.executor.workerprofile.name

        # search for default worker profile
        try:
            return WorkerProfile.objects.get(is_default=True).name
        except (WorkerProfile.DoesNotExist, WorkerProfile.MultipleObjectsReturned):
            return None

    @property
    def failed(self):
        return self.state == Execution.STATE_FAILED

    @property
    def finished(self):
        return self.state == Execution.STATE_FINISHED
