===============
Getting started
===============

This page describes how to set up a fresh instance of the platform via Docker Compose, create the first user, and import a base configuration (entity types, executors, ...) so there is something to run. It assumes Docker (or another OCI-compatible runtime) and Docker Compose are installed.

The compose setup under ``deployment/`` is the recommended way to run the platform - it starts the app, its Celery workers/beat, PostgreSQL and RabbitMQ together.
For running the app directly on the host during development instead, see :doc:`../development/index`.

Configure
=========

.. code-block:: shell

   cd deployment

``deployment/.env`` contains the configuration values that should be adjusted (``deployment/.env.static`` contains values that normally don't need to change):

* ``SECRET_KEY`` - change this to a random value (recommendation: ``pwgen -s 64 1``)
* ``POSTGRES_PASSWORD`` / ``RABBITMQ_PASSWORD`` - change these from the defaults.
* ``ALLOWED_HOSTS`` - add the hostname(s) you will reach the app under, if not just
  ``localhost``.
* ``TIME_ZONE`` - used for displaying timestamps in the web UI.

The database password is only picked up by PostgreSQL on its very first start (it initializes the volume then).
Changing it later means changing it manually inside the container as well, not just in ``.env``.

Start the platform
==================

.. code-block:: shell

   docker compose -f compose-platform-default-workers.yml up -d

This starts all required components:

* ``app`` - the web app (``http://localhost:8000``), also initializes the database
* ``app-celery`` - worker for central and periodic tasks
* ``app-worker-low`` / ``-medium`` / ``-high`` - Celery workers, one per worker profile queue (we assume here the queues are called ``low``, ``medium`` and ``high``)
* ``db`` - PostgreSQL
* ``mq`` - RabbitMQ

Artifacts and temporary execution data are stored on the host under ``deployment/data/`` so that they are easily accessible.
The database data is stored in a Docker volume.

.. important::
   The worker containers mount the host's Docker socket.
   This is required to start the containers for the executors.

Create a user
=============

.. code-block:: shell

   docker compose -f compose-platform-default-workers.yml exec app ./manage.py createsuperuser

Follow the prompts - the email address is not required.
Afterwards, you can log into the web UI at ``http://localhost:8000`` with the created account.
Further users then can be created via the web UI.

Import a base configuration
============================

A fresh instance has no entity types, executors or config options yet.
The folder ``configuration/`` in the Git repository is a working example set with entity types like ``domain`` or ``ipv4_address``, executors wrapping ``nmap``,
``dnsx``, ``subfinder``, ``tlsx``, and their default config.
For an easy import, the script ``configuration/import.sh`` can be used, which uses the ``sqg`` CLI.

First, create an API token in the web UI and configure the CLI.

.. code-block:: shell

   sqg login

Then import the configuration:

.. code-block:: shell

   cd configuration
   ./import.sh

Re-running the import is safe - objects are matched and updated by name, not duplicated.

See :doc:`../usage/cli` for the ``sqg import``/``sqg config`` commands this script
uses, and :doc:`../usage/executors` for what an executor container itself has to do.

Next steps
==========

* :doc:`../usage/executors` - how an executor container works, for writing your own.
* :doc:`../usage/cli` - the full CLI reference.
* :doc:`../api/index` - the REST API.
