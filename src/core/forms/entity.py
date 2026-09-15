from django import forms

from ..models import Entity
from .widgets import ButtonGroupWidget, JedisonWidget


class EntityForm(forms.ModelForm):
    """
    Edit entity with Jedison as frontend editor.
    """

    class Meta:
        model = Entity
        fields = ["state", "data"]

    def __init__(self, *args, entitytype, **kwargs):
        super().__init__(*args, **kwargs)

        # default state to enabled, independent of the approval required flag
        # if an user adds an entity, it probably should be there
        if self.instance.pk is None:
            self.initial["state"] = Entity.STATE_ENABLED

        # add entitytype name to schema, so that editor shows it
        entitytype_schema = entitytype.schema
        entitytype_schema["title"] = entitytype.name

        # widgets + remove labels
        self.fields["state"].widget = ButtonGroupWidget(choices=self.fields["state"].choices)
        self.fields["state"].label = False

        self.fields["data"].widget = JedisonWidget(schema=entitytype_schema)
        self.fields["data"].label = False
