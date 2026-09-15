from django import forms


class JedisonWidget(forms.Widget):
    """
    Widget using Jedison editor: Edit JSON data based on fixed JSON schema.

    The form is only rendered in the frontend, the HTTP requests still contain JSON.
    """

    template_name = "core/widgets/jedison_widget.html"

    def __init__(self, schema, attrs=None):
        self.schema = schema
        super().__init__(attrs)

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        widget = context["widget"]
        widget["schema"] = self.schema
        widget["schema_script_id"] = f"{widget['attrs']['id']}-schema"
        return context


class ButtonGroupWidget(forms.Widget):
    """
    Renders choices as a Bootstrap 5 button group

    The blank choice Django adds to a required ChoiceField without a model default (rendered
    as e.g. "---------" by a <select>) is dropped.
    """

    template_name = "core/widgets/button_group_widget.html"

    def __init__(self, choices, attrs=None):
        # drop default empty choice
        self.choices = [(value, label) for value, label in choices if value not in (None, "")]
        super().__init__(attrs)

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        widget = context["widget"]
        widget["options"] = [
            {
                "id": f"{widget['attrs']['id']}_{i}",
                "value": choice_value,
                "label": choice_label,
                "checked": str(choice_value) == str(value),
            }
            for i, (choice_value, choice_label) in enumerate(self.choices)
        ]
        return context
