#!/usr/bin/env bash
#
# Startup script for the squiggle-automation docker image. The same image is
# used for the app, celery beat and every celery worker queue - only the
# mode (first argument) and its parameters differ:
#
#   app                the django app, served via uwsgi
#   beat                celery beat (periodic task scheduler)
#   worker <queue>      a celery worker consuming <queue>
#   manage <args...>    ad-hoc "python manage.py <args...>" (migrate, createsuperuser, ...)

set -euo pipefail

mode="${1:-}"
shift || true

case "$mode" in
    app)
        python manage.py migrate --noinput
        python manage.py createcachetable
        python manage.py collectstatic --noinput
        exec uwsgi \
            --http "0.0.0.0:8000" \
            --module squiggle_automation.wsgi:application \
            --master \
            --processes 4 \
            --static-map /static=static
        ;;

    beat)
        exec celery -A squiggle_automation worker --loglevel=info -B
        ;;

    worker)
        queue="${1:-}"
        if [ -z "$queue" ]; then
            echo "usage: $0 worker <queue>" >&2
            exit 1
        fi

        # The worker can fail to start before migrations have run and the queue's config exists in the database
        # Retry instead of crash-looping the container
        #
        # %h is expanded by celery itself to the container's hostname, keeping
        # node names unique if a queue is ever scaled to multiple replicas
        until celery -A squiggle_automation worker --loglevel=info -Q "$queue" -n "worker-$queue@%h"; do
            echo "celery worker for queue '$queue' exited, retrying in 30s..." >&2
            sleep 30
        done
        ;;

    manage)
        exec python manage.py "$@"
        ;;

esac
