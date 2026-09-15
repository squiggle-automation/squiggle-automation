=========
Executors
=========

Concept
=======

An **executor** is a container (Docker, Podman, or any other OCI-compatible runtime) that
wraps a single tool and makes it usable by the platform.

The container receives:

* the **entities** that should be processed, and
* its **configuration**

as input. Its job is to run the wrapped tool and return:

* **new entities** as output, and
* optionally **log messages** (infos, warnings, errors),
* optionally **artifacts** (raw tool output files).

Everything is exchanged through the file system - an executor does not need network access to
the platform itself.

A single executor run looks like this:

#. The platform prepares ``/data/input/data.json`` and starts the container.
#. The container reads its input, runs the tool, and processes the tool's output.
#. Relevant tool output is written to files as artifacts.
#. The container writes ``/data/output/data.json`` and exits.
#. The platform reads the output file, ingests the new entities, and stores the artifacts.

Container specification
=======================

Directory layout
----------------

``/data/input/data.json``
^^^^^^^^^^^^^^^^^^^^^^^^^

``data.json`` contains the input entities and the configuration.
Written by the platform before the container starts.
See the data format section below.

``/data/output/data.json``
^^^^^^^^^^^^^^^^^^^^^^^^^^

Written by the executor before it exits. See the data format section below. If this file is
missing or not valid JSON, the run is treated as failed.

``/data/tmp``
^^^^^^^^^^^^^

All temporary files must be placed here, especially large ones.
Do not write to ``/tmp``, to the home directory, or anywhere else inside the container's own file system layer — the container root is not meant to hold significant amounts of data.
``/data/tmp`` is discarded after the run (except the executor is configured to keep the temporary files after execution).

``/data/artifacts``
^^^^^^^^^^^^^^^^^^^

Every output file that should be preserved goes here.
This can be output files that are later used or tool output to verify that the tool was executed succesfully.

Two common cases:

* **Tools with native output files.** Some tools produce good machine- and human-readable
  output on their own (for example ``nmap -oA``, or ``testssl.sh --logfile/--jsonfile``). Point
  them directly at ``/data/artifacts`` and let them write there.
* **Tools that only write to the terminal.** For everything else, pipe ``stdout`` and ``stderr``
  into files under ``/data/artifacts``, for example:

  .. code-block:: bash

     mytool --target example.com > /data/artifacts/mytool.stdout 2> /data/artifacts/mytool.stderr

Data format
-----------

Both JSON files are UTF-8 encoded.

Input: ``/data/input/data.json``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: json

   {
     "data": {
       "<entitytype>": [
         { "<attribute>": "<value>" },
         { "<attribute>": "<value>" }
       ]
     },
     "configuration": {
       "<option>": "<value>"
     }
   }

* ``data`` — an object mapping an entity type name to a list of entities of that type. Each
  entity is an object with the attributes of that type.
* ``configuration`` — a flat object of configuration options for this run. Values are strings.

Example:

.. code-block:: json

   {
     "data": {
       "ipv4_address": [
         { "address": "10.0.0.1" },
         { "address": "10.0.0.2" },
       ]
     },
     "configuration": {
       "portscan_ports": "80,443",
       "portscan_protocol": "tcp"
     }
   }

Output: ``/data/output/data.json``
----------------------------------

.. code-block:: json

   {
     "errors": ["..."],
     "warnings": ["..."],
     "infos": ["..."],
     "data": {
       "<entitytype>": [
         { "<attribute>": "<value>" }
       ]
     }
   }

* ``errors`` — error messages. A non-empty list marks the run as failed.
* ``warnings`` — messages about problems that did not stop the run.
* ``infos`` — informational messages, useful for progress and context.
* ``data`` — the new entities produced by this run, in the same format as the input ``data``.

Example:

.. code-block:: json

   {
     "errors": [],
     "warnings": [],
     "infos": ["no route to host 10.0.0.1"],
     "data": {
       "service": [
         { "ip": "10.0.0.2", "port": "80", "protocol": "tcp", "name": "http" },
         { "ip": "10.0.0.2", "port": "443", "protocol": "tcp", "name": "https" }
       ]
     }
   }

Error handling / Exit code
--------------------------

The exit code is **not** the primary way to report a failure.

Reporting an error message via the output file is what marks a run as failed.
An executor that detects an error, writes it into ``data.json``, and exits with code ``0`` is behaving correctly.

Base image
==========

Executors are usually built with the provided ``executor-base`` image that also provides a Python library for parsing the input ``data.json`` and writing the output ``data.json``.
The base images uses Debian Trixie and has a few common utilities (like ``jq``, ``wget``, ``curl``, ``unzip``) already installed.

To build a new executor, derive from this image, install the tool, and replace
``/root/entrypoint.py``:

.. code-block:: dockerfile

   FROM executor-base:latest

   RUN apt update && apt install -y nmap && apt clean

   COPY entrypoint.py /root/entrypoint.py

``entrypoint.py`` is executed directly, so it needs a shebang (``#!/usr/bin/env python3``) and
the executable bit.

You can build your executor also with other base images, it this is required.
In general, we recommend to use our base image and the provided Python library.

The ``executor_helper`` Python library
======================================

The ``executor_helper`` Python library provides the ``ExecutorHelper`` class with several useful methods.
When writing the entrypoint in Python, it can be imported as:

.. code-block:: python

   from executor_helper import ExecutorHelper

Input and output
----------------

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Method
     - Description
   * - ``read_input()``
     - Reads ``/data/input/data.json`` and populates the input entities and the configuration.
   * - ``write_output()``
     - Writes the collected messages and output entities to ``/data/output/data.json``.

``read_input()`` must be called before any configuration or entity access, and
``write_output()`` must be called exactly once, at the very end of the run.

Configuration
-------------

.. list-table::
   :header-rows: 1
   :widths: 40 60

   * - Method
     - Description
   * - ``get_config(name, default=None, required=False)``
     - Returns the raw value. With ``required=True``, a missing value adds an error.
   * - ``get_config_bool(name, default=None, required=False)``
     - Parses ``0``/``1``, ``false``/``true``, ``no``/``yes`` (case-insensitive) into a boolean.
       Any other value adds an error and returns ``None``.
   * - ``get_config_choices(name, default=None, required=False, choices=[])``
     - Validates the value against ``choices`` (case-insensitive) and returns it lower-cased.
       An invalid value adds an error and returns ``None``.

Note that these methods record an error rather than raising an exception, so validation
does not interrupt the flow.
Read all configuration first, then call ``exit_on_error()`` once - that way the user sees every configuration problem at once instead of one per run.

Entities
--------

.. list-table::
   :header-rows: 1
   :widths: 35 65

   * - Method
     - Description
   * - ``get_input_entities(entitytype)``
     - Returns the list of input entities of that type, or an empty list if there are none.
   * - ``add_output_entity(entitytype, data)``
     - Adds one output entity.

Logging
-------

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Method
     - Description
   * - ``add_error(message)``
     - Records an error. Any error marks the run as failed.
   * - ``add_warning(message)``
     - Records a warning. The run continues and is not marked as failed.
   * - ``add_info(message)``
     - Records an informational message.

Error handling
--------------

.. code-block:: python

   e.exit_on_error()

If at least one error has been recorded, ``exit_on_error()`` writes the output file and
terminates the process.

Call it after configuration parsing, and after any step where continuing would not make
sense.

Example entrypoint
==================

.. code-block:: python

   #!/usr/bin/env python3

   from executor_helper import ExecutorHelper

   # init helper and read input
   executor = ExecutorHelper()
   executor.read_input()

   # get config parameters
   dns_resolver = executor.get_config("dns_resolver", "8.8.8.8")
   executor.exit_on_error()

   # iterate over input entities and do work
   domains = executor.get_input_entities("domain")

   # ... run the tool, let it write artifacts to /data/artifacts

   # ... read output

   for i in ipv4_results:
      executor.add_output_entity("ipv4_address", {"address": i})

   # write output file
   executor.write_output()

Testing
=======

Executor logic depends on tools (``nmap``, ``dig``, ...) that might only exist *inside* the built
container image, not on the development host. Testing therefore happens at the container level:
build the real image, run it for real against a controlled target, and check what comes out.

Test cases live next to each executor, in ``executors/<name>/tests/<case>/``:

* ``input.json`` - the input document for this case.
* ``expected_output.json`` - what the executor is expected to produce.

Additional files:
* ``executors/<name>/tests/cap_net_raw`` - optional, empty marker file for the whole executor; if present, every case's container is run with ``--cap-add NET_RAW`` (mirrors the
``cap_net_raw`` setting in the application).

Usage, from ``executors/``:

.. code-block:: shell

   just test <executor>                 # build + run every case for one executor
   just test <executor> <case>          # run a single case
   just test-all                        # every case, every executor
   just testenv-down                    # tear down the target containers

The test environment is started automatically, but needs to be stopped manually (``just testenv-down``).

The above ``just`` recipes are this repo's convenience wrapper - the actual build/test logic
lives in the :doc:`CLI <cli>` (``sqg executor build``/``sqg executor test``), which works
from the current directory and isn't specific to this repo's layout. This matters once executor
definitions move into their own repositories: the CLI is what those would use directly, without
needing this repo's justfile at all. It does not manage the target/network side of testing
(``executors/_testenvironment/``) - that stays a concern of whichever repo owns the test
environment.

Not every executor can be tested this way - some might depend on live data from the internet, some might require a bigger test infrastrucutre that cannot be easily started in containers.

The test environment lives under ``executors/_testenvironment/`` and can be extended with further containers.

Guidelines
==========

* Write output exactly once - Every code path must end in ``write_output()`` or in
  ``exit_on_error()``, which writes the file itself. A run without an output file is a failed
  run.
* Fail loudly, not silently -  If the tool cannot run at all, add an error. If a single
  input entity could not be processed, add a warning and continue with the rest.
* Log enough to be debuggable - Info messages should let a reader reconstruct what
  happened without opening the artifacts; the artifacts should let them go deeper.
* Keep large data out of the container layer -  Temporary files belong in ``/data/tmp``,
  results in ``/data/artifacts``.
* Be idempotent and stateless - An executor gets no memory of previous runs; everything it
  needs comes from the input file.
