from django import forms


class ProjectSwitchForm(forms.Form):
    project = forms.IntegerField(widget=forms.HiddenInput())

    def __init__(self, project, *args, **kwargs):
        kwargs.update(
            initial={
                "project": project.pk,
            }
        )

        super().__init__(*args, **kwargs)
