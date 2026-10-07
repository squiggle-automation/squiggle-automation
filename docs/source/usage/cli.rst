===
CLI
===

``sqg`` is a command-line tool for the platform's REST API, and for building/testing
executor container images.

You can run it directly from the ``cli`` directory, or install it via ``pyproject.toml``.

Run it directly - needs nothing beyond the standard library:

.. code-block:: shell

   python3 cli/cli.py ...

Or install it (e.g. into a venv, or as a pipx tool) as a ``sqg`` command:

.. code-block:: shell

   cd cli

   pip install .
   # or
   pipx install .

   sqg ...

.. note::
   If ``sqg`` is not found right after ``pipx install .``, pipx's binary directory is probably not on your ``PATH`` yet.
   Run ``pipx ensurepath`` and open a new shell (or re-source your shell config).

The following documentation assumes that the CLI can be called with the command ``sqg``.

Authentication
==============

.. code-block:: shell

   sqg login

Prompts for the API URL and a token (generate one for your user via the web UI's "API token"
page), verifies them against the API, and stores them in ``~/.sqg.json`` for
every other command to reuse. Re-running ``login`` shows the stored values (the token
masked), and keeps each one if the input is left empty.

Optionally, a default project id can be given.

This is not required for executor builds and tests (no API communication required).

Importing objects
==================

.. code-block:: shell

   sqg import <datatype> <folder>

``<datatype>`` is one of ``entitytypes``, ``configoptions``, ``containers``, ``executors``, ``workerprofiles``.

``<folder>`` contains one ``.json`` file per object in the format that is also used by the API.
The JSON content can also be displayed in the web UI.

Re-running an import is safe, the object it either created or updated.
The ``"name"`` field is used to identify the object.

Since executors reference containers, entity types and worker profiles by name, and containers
reference config options, import order matters when setting up from scratch.
It is recommended to create a custom import script like ``configuration/import.sh``.

Entities
========

.. code-block:: shell

   sqg entity get <entitytype> [--project ID] [--state enabled|waiting_approval|disabled|all]
   sqg entity add <entitytype> [--project ID] key=value [key:=json ...]
   sqg entity add <entitytype> [--project ID] --file <path|->

``<entitytype>`` is the name of the entity type (e.g. ``domain``). ``--project`` defaults to the project stored by ``login``.

``get`` prints the entities as JSON (``[{"data": {...}, "state": "..."}]``), by default only the enabled ones - ``--state all`` prints all of them:

.. code-block:: shell

   sqg entity get domain | jq -r '.[].data.name'

``add`` adds a single entity from ``key=value`` (string) and ``key:=json`` (typed, e.g. ``port:=443``) fields,
or entities from ``--file``: a ``.json`` file, a folder of ``.json`` files, or ``-`` for stdin, each holding one
entity (``{"data": {...}}``) or a list of them - the format ``get`` prints:

.. code-block:: shell

   sqg entity add service address=1.2.3.4 port:=443 protocol=tcp
   sqg entity get domain --project 1 | sqg entity add domain --project 2 --file -

Each entity is reported as ``created`` or ``updated`` - entities are identified by the identifier keys of their entity type, so re-running ``add`` is safe.
New entities follow the approval settings of the entity type, existing ones keep their state.

Config values
=============

.. code-block:: shell

   sqg config set <option> [value] [--executor NAME]
   sqg config get <option> [--executor NAME]

Reads or writes the value of one config option - globally (the default every executor falls
back to) by default, or for one executor with ``--executor``. On ``set``, omitting ``value``
clears it instead of setting it.

Building executors
==================

.. code-block:: shell

   sqg executor build --all
   sqg executor build <name>
   sqg executor test --all
   sqg executor test <name> [<case>]
   sqg executor push [--dry-run] --all
   sqg executor push [--dry-run] <name>

These operate on executor directories in the **current working directory** - ``<name>`` must be a subdirectory right there.

``build`` runs a plain ``docker/podman build`` on ``<name>/container``, tagged ``executor-<name>``.

``test`` runs each fixture under ``<name>/tests/<case>/`` against the already-built image and verifies the result - see :doc:`executors` for the fixture format.
It assumes the image is already built and that the test environment is ready - it does not build anything or manage that environment - see :doc:`executors`'s Testing section and ``just testenv-up`` for how this repo provides it.

``push`` runs a plain ``docker/podman push`` on the image ``build`` produced.
It does not build anything - build first.
The image is pushed under exactly the name it was built with, so to push into a registry, set the ``container.prefix`` in ``config.json`` to include it (e.g. ``registry.example.com/team/executor``, which makes ``build`` tag and ``push`` push ``registry.example.com/team/executor-nmap``).
Authentication is left to the runtime - log in with ``docker/podman login`` beforehand.
With ``--dry-run``, the images that would be pushed are printed and nothing is pushed.

Environment variables:

* ``CONTAINER_RUNTIME`` - overrides the docker/podman-if-present auto-detection.
* ``KEEP_TMP=1`` - keeps a test case's temporary work directory instead of deleting it after the run, for inspecting the ``/data/...`` directories after a failure.

In the main repo, ``executors/justfile`` wraps these commands for local convenience (``just build``, ``just push``, ``just test``, ...) and also owns the test target environment - see :doc:`executors`.
