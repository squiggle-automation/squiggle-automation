from celery import shared_task

from squiggle_automation.celery import app


@shared_task(bind=True)
def set_worker_concurrency(self, queue_name: str, concurrency: int):
    """
    Set concurrency on every worker that handles the specified queue.
    """
    inspect = app.control.inspect(timeout=5.0)

    # find workers that consume the queue
    active_queues = inspect.active_queues() or {}
    workers = [worker for worker, queues in active_queues.items() if any(q["name"] == queue_name for q in queues)]

    if not workers:
        return

    # get current concurrency per worker
    stats = inspect.stats() or {}

    for worker in workers:
        # get current currency based on the number of processes
        # the max-concurrency attribute does not work, it is not updated
        pool = stats.get(worker, {}).get("pool", {})
        processes = pool.get("processes")
        if not isinstance(processes, list):
            # prefork is not used, pool_grow/pool_shrink does not work here
            continue
        current = len(processes)

        # set new concurrency
        delta = concurrency - current
        if delta > 0:
            app.control.pool_grow(delta, destination=[worker])
        elif delta < 0:
            app.control.pool_shrink(-delta, destination=[worker])
