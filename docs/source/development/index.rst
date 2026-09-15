===========
Development
===========

For just running the platform, use the Docker Compose setup in :doc:`../getting-started/index`
instead - this page is about running the app directly on the host, e.g. for development.

Running without Docker
=======================

PostgreSQL and RabbitMQ can be started with Docker Compose using ``deployment/compose-testing-db-mq-only.yml``.
It only starts those both services and exposes them on their default host ports instead of running the app itself.
It also uses the credentials from ``deployment/.env``, so adapt that if you wish.

.. code-block:: shell

   cd deployment
   docker compose -f compose-testing-db-mq-only.yml up -d

If you want to change credentials for the Django app, you can copy ``src/.env.example`` to ``.env``.

By default, the test credentials for Django and the Docker Compose file match, so no change required.

To run the entire app:

.. code-block:: shell

   cd src
   python3 ./manage.py migrate
   python3 ./manage.py createcachetable
   python3 ./manage.py runserver

   celery -A squiggle_automation worker --loglevel=info -B
   celery -A squiggle_automation worker --loglevel=info -Q low -n worker-low
   celery -A squiggle_automation worker --loglevel=info -Q medium -n worker-medium
   celery -A squiggle_automation worker --loglevel=info -Q high -n worker-high

If you do not need any executions, you can skip running Celery.

Tests
=====

Run via Django's own test runner:

.. code-block:: shell

   cd src
   python3 ./manage.py test
