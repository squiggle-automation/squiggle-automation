from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.utils.translation import gettext_lazy as _

from ..tasks import set_worker_concurrency


def validate_not_default(value):
    if value.lower() == "default":
        raise ValidationError('"default" is not an allowed value.')


# NOTE: this model is edited via both a web form (fields=[...] on WorkerProfileCreateView/
# WorkerProfileUpdateView in core/views/workerprofile.py) and an API serializer
# (api/serializers/workerprofile.py). If you add, remove, or rename a field, update both.
class WorkerProfile(models.Model):
    class Meta:
        ordering = ["name"]

    name = models.CharField(
        max_length=255,
        blank=False,
        null=False,
        unique=True,
        validators=[validate_not_default],
        verbose_name=_("Name"),
        help_text=_("Queue name for Celery workers"),
    )

    concurrency = models.PositiveIntegerField(
        default=5,
        validators=[MinValueValidator(1)],
        verbose_name=_("Concurrency"),
    )

    is_default = models.BooleanField(
        default=False,
        verbose_name=_("Default worker"),
    )

    def __str__(self):
        return self.name

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._old_concurrency = self.concurrency

    def save(self, *args, **kwargs):
        with transaction.atomic():
            others_qs = WorkerProfile.objects.select_for_update().exclude(pk=self.pk)

            if self.is_default:
                # this worker is becoming the default, so remove default on all other workers
                others_qs.filter(is_default=True).update(is_default=False)
            elif not others_qs.filter(is_default=True).exists():
                # no other default exists, this is the new default
                self.is_default = True

            super().save(*args, **kwargs)

            # trigger task that updates tha concurrency if it changed
            if self._old_concurrency != self.concurrency:
                transaction.on_commit(lambda: set_worker_concurrency.delay(self.name, self.concurrency))

        self._old_concurrency = self.concurrency

    def delete(self, *args, **kwargs):
        if self.is_default:
            raise ValidationError(_("Cannot delete the default worker"))
        return super().delete(*args, **kwargs)
