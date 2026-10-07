import json
import os
import random
import shutil
import string

import docker
from celery import shared_task
from django.conf import settings

from core.exceptions import (
    ExecutionCancledError,
    ExecutionError,
    ExecutionOutputError,
    ExecutionRuntimeError,
)
from core.models import (
    SENSITIVE_VALUE_MASK,
    Entity,
    EntityType,
    Event,
    Execution,
    ExecutionLog,
)


@shared_task(bind=True)
def run_executor(self, execution_id):
    # get data from database
    execution = Execution.objects.get(id=execution_id)
    project = execution.project
    executor = execution.executor
    entities = execution.entities

    # the execution might have been aborted while it was waiting in the queue
    # this does not raise an exception (compared to disabled executor etc. below) but just silently exits
    # raising an exception causes the state failed, which allows to re-schedule the task. this is not intended here
    if execution.aborted:
        return

    try:
        # check if executor is still enabled (maybe this changed since the execution was queued)
        if not executor.enabled:
            raise ExecutionCancledError("executor is disabled")

        # check if executions for project should still be running (maybe this changed since the execution was queued)
        if not project.run_executors:
            raise ExecutionCancledError("running executors disabled in project")

        # set execution to running
        execution.update_state(Execution.STATE_RUNNING)

        # get used input entitytpes
        # this compares provided and supported entity types and raises an exception if it does not match
        used_entitytypes = execution.get_used_input_entitytypes()

        # create temporary folder
        work_dir_artifacts, work_dir_input, work_dir_output, work_dir_tmp = execution.create_work_directories()

        # resolve the config values that apply to this executor, store a masked copy for the record
        configuration, masked_configuration = _get_configuration(executor)
        execution.applied_config = masked_configuration  # will be saved with next state update

        # create input files
        _create_input_data(work_dir_input, configuration, entities, used_entitytypes)

        # run container
        _run_container(execution, executor.container, work_dir_artifacts, work_dir_input, work_dir_output, work_dir_tmp)

        # read output data and put it into database
        execution.update_state(Execution.STATE_PROCESSING_RESULTS)
        _process_output_data(work_dir_output, project, execution, executor)

        # set execution to finished
        execution.update_state(Execution.STATE_FINISHED)
    except ExecutionError as e:
        execution.add_log(ExecutionLog.LEVEL_ERROR, e)
        execution.update_state(Execution.STATE_FAILED)

    # delete tmp files
    if not executor.keep_tmp_files:
        shutil.rmtree(execution.tmp_directory, ignore_errors=True)


def _get_configuration(executor):
    """
    Resolve the config values that apply to this executor.

    Returns a tuple (configuration, masked_configuration): both are {name: value} dicts, but in
    masked_configuration the value of sensitive config options is replaced by SENSITIVE_VALUE_MASK.
    """
    configuration = {}
    masked_configuration = {}
    for c in executor.container.configoptions.all():
        value = c.get_value(executor)
        configuration[c.name] = value.value if value else None
        if value and c.sensitive:
            masked_configuration[c.name] = SENSITIVE_VALUE_MASK
        else:
            masked_configuration[c.name] = configuration[c.name]
    return configuration, masked_configuration


def _create_input_data(work_dir, configuration, entities, used_entitytypes):
    # group entites by entitytype
    input_data_entities = {}
    for entitytype in used_entitytypes:
        entitytype_name = EntityType.objects.get(pk=entitytype).name
        # get data of all entities of this type
        input_data_entities[entitytype_name] = list(
            entities.filter(entitytype=entitytype).values_list("data", flat=True)
        )

    # build final data structure
    intput_data = {
        "data": input_data_entities,
        "configuration": configuration,
    }

    # write file
    with open(os.path.join(work_dir, "data.json"), "w") as f:
        json.dump(intput_data, f)


def _run_container(execution, container, work_dir_artifacts, work_dir_input, work_dir_output, work_dir_tmp):
    work_dir_artifacts_full = _get_host_path(
        work_dir_artifacts, settings.ARTIFACTS_DIR, settings.ARTIFACTS_DIR_HOST_OVERRIDE
    )
    work_dir_input_full = _get_host_path(work_dir_input, settings.TMP_DIR, settings.TMP_DIR_HOST_OVERRIDE)
    work_dir_output_full = _get_host_path(work_dir_output, settings.TMP_DIR, settings.TMP_DIR_HOST_OVERRIDE)
    work_dir_tmp_full = _get_host_path(work_dir_tmp, settings.TMP_DIR, settings.TMP_DIR_HOST_OVERRIDE)

    # generate container name
    # as we include the execution id and remove the container on errors, the random part should not be required
    # but better safe than sorry
    container_name_random = "".join(random.choices(string.ascii_lowercase, k=6))
    container_name = f"execution_{execution.executor.name}_{execution.id}_{container_name_random}"

    # set capabilities based on config
    cap_list = []
    if container.cap_net_raw:
        cap_list.append("NET_RAW")

    # use host network based on config
    network_mode = "host" if container.net_host else None

    try:
        docker_client = docker.from_env()
        docker_client.containers.run(
            f"{container.image}:{container.image_tag}",
            name=container_name,
            volumes={
                work_dir_artifacts_full: {"bind": "/data/artifacts", "mode": "rw"},
                work_dir_input_full: {"bind": "/data/input", "mode": "rw"},
                work_dir_output_full: {"bind": "/data/output", "mode": "rw"},
                work_dir_tmp_full: {"bind": "/data/tmp", "mode": "rw"},
            },
            cap_add=cap_list,
            network_mode=network_mode,
        )
        # store stdout?
    except docker.errors.ImageNotFound:
        raise ExecutionRuntimeError("container image not found")
    except docker.errors.ContainerError as e:
        raise ExecutionRuntimeError("container returned error: \n\n" + e.stderr.decode("utf-8"))
    except docker.errors.APIError as e:
        raise ExecutionRuntimeError("container failed to start: \n\n" + str(e))
    finally:
        try:
            c = docker_client.containers.get(container_name)
            c.remove()
        except (docker.errors.NotFound, docker.errors.APIError):
            # the executor should not fail even if the container was not removed
            pass


def _process_output_data(work_dir_output, project, execution, executor):
    error_found = False

    try:
        with open(os.path.join(work_dir_output, "data.json"), "r") as f:
            data = json.load(f)

            # get error, warning and info log entries
            for i in data.get("errors", []):
                execution.add_log(ExecutionLog.LEVEL_ERROR, i)
                error_found = True
            for i in data.get("warnings", []):
                execution.add_log(ExecutionLog.LEVEL_WARNING, i)
            for i in data.get("infos", []):
                execution.add_log(ExecutionLog.LEVEL_INFO, i)

            # get list of excpected entitytypes
            entitytypes_expected = set(executor.output.values_list("name", flat=True))

            # get output entities
            entity_data = None
            try:
                entity_data = data["data"].items()
            except KeyError:
                raise ExecutionOutputError('failed to parse output data: "data" not found')

            for entitytype_name, entity_list in entity_data:
                # try to get the entitytype. if it is not known, log an error
                try:
                    entitytype = EntityType.objects.get(name=entitytype_name)
                except EntityType.DoesNotExist:
                    execution.add_log(ExecutionLog.LEVEL_ERROR, f"returned entity type \”{entitytype_name}\” not found")
                    continue

                # check that entity type is allowed
                # if not, log an warning (maybe the user does not want to have an entity type that the container could return)
                if entitytype_name not in entitytypes_expected:
                    execution.add_log(
                        ExecutionLog.LEVEL_WARNING, f"returned entity type \”{entitytype_name}\” not expected as output"
                    )
                    continue

                # go through list and add to db
                for entity_item in entity_list:
                    try:
                        Entity.objects.upsert_entity(entitytype, project, entity_item)
                    except ValueError:  # TODO: complete?
                        execution.add_log(ExecutionLog.LEVEL_ERROR, "failed to add data: " + json.dumps(entity_item))
    except FileNotFoundError:
        raise ExecutionOutputError("output file not found")

    if error_found:
        raise ExecutionRuntimeError(
            "error messages were returned"
        )  # TODO: this is logged as error -> one error leads to 2 errors


def _get_host_path(input_path, base_path, base_override_path):
    # the input_path should be mapped into the executor container
    # input_path could be relative or absolute, depending on the ARTIFACT/TMP_PATH settings
    #
    # we need to provide an absolute path to docker
    #
    # additionally, the path on the docker host might be different, provided in ARTIFACT/TMP_PATH_HOST_OVERRIDE
    # in this case we map from for example ARTIFACT_PATH/project_1/example/dir to ARTIFACT_PATH_HOST_OVERRIDE/project_1/example/dir
    # ARTIFACT/TMP_PATH is provided as base_path, ARTIFACT/TMP_PATH_HOST_OVERRIDE is provided as override path

    input_path_absolute = os.path.abspath(input_path)

    if base_override_path:
        # remove base_path from front, add base_override_path
        relative_path = os.path.relpath(input_path_absolute, base_path)
        return os.path.join(base_override_path, relative_path)

    return input_path_absolute
