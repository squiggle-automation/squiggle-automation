from django.db import models
from django.utils.translation import gettext_lazy as _


# NOTE: this model is edited via both a web form (fields=[...] on ProjectCreateView/
# ProjectUpdateView in core/views/project.py) and an API serializer (api/serializers/project.py).
# If you add, remove, or rename a field, update both.
class Project(models.Model):
    class Meta:
        ordering = ["name"]

    name = models.CharField(
        max_length=255,
        blank=False,
        null=False,
        unique=True,
        verbose_name=_("Name"),
    )

    run_executors = models.BooleanField(
        default=True,
        verbose_name=_("Run executors"),
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        adding = self._state.adding

        super().save(*args, **kwargs)

        # if newly added, create indexes of this project
        if adding:
            from .entity import create_index

            create_index(
                project_list=[
                    self,
                ]
            )

    def delete(self, *args, **kwargs):
        old_id = self.id
        super().delete(*args, **kwargs)

        # delete indexes for this project
        from .entity import delete_index

        delete_index(project_deleted=old_id)
