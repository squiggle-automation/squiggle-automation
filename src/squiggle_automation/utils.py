import time
from contextlib import contextmanager

from django.contrib.auth.mixins import UserPassesTestMixin
from django.core.cache import caches


class SuperuserRequiredMixing(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_superuser


@contextmanager
def cache_lock(lock_id, oid, expire=60 * 10):
    """
    A lock based on the Django caching functionality. Used in some Celery tasks to prevent
    the parallel execution of the same task.

    Source: https://docs.celeryproject.org/en/latest/tutorials/task-cookbook.html

    We use the database cache backend here, this is not as good as using memcached,
    but should be good enough for the use case. By default, the lock expires after 10 minutes.
    """
    timeout_at = time.monotonic() + expire - 3
    # cache.add fails if the key already exists
    status = caches["locks"].add(lock_id, oid, expire)
    try:
        yield status
    finally:
        if time.monotonic() < timeout_at and status:
            # don't release the lock if we exceeded the timeout
            # to lessen the chance of releasing an expired lock
            # owned by someone else
            # also don't release the lock if we didn't acquire it
            caches["locks"].delete(lock_id)
