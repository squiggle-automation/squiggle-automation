from celery import shared_task

from core.models import AutoApprovalRule

# TODO: log errors, show them, etc. (see run_event_handler.py)


@shared_task
def run_auto_approval_rule(autoapprovalrule_id):
    """
    Applies an auto-approval rule to every entity that is currently waiting for approval (inside the project).

    Triggered via "Run now" button in web interface.
    """
    try:
        rule = AutoApprovalRule.objects.get(pk=autoapprovalrule_id)
    except AutoApprovalRule.DoesNotExist:
        return  # rule was deleted before this task ran

    rule.run_on_waiting_entities()
