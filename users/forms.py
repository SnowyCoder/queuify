
from django import forms
from django.contrib.auth.forms import UserCreationForm
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Div, Fieldset
from crispy_bootstrap5.bootstrap5 import FloatingField

from core.utils import crispy_save_or_go_back

from .models import User

class EditUserForm(forms.ModelForm):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self.helper = FormHelper()
        self.helper.layout = Layout(
            Fieldset("Profile edit",
                Div(
                    Div(FloatingField('first_name'), css_class="col"),
                    Div(FloatingField('last_name'), css_class="col"),
                    Div(FloatingField('pronouns'), css_class="col"),
                    css_class="row",
                ),
                FloatingField('description'),
                'image',
                'tz',
            ),
            crispy_save_or_go_back(),
        )

    class Meta:
        model = User
        fields = ('first_name', 'last_name', 'pronouns', 'description', 'image', 'tz')

class CreateUserForm(UserCreationForm):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self.helper = FormHelper()
        self.helper.layout = Layout(
            Fieldset("Create user",
                'username',
                Div(
                    Div(FloatingField('first_name'), css_class="col"),
                    Div(FloatingField('last_name'), css_class="col"),
                    css_class="row",
                ),
                'password1',
                'password2',
            ),
            crispy_save_or_go_back('Sign in!'),
        )

    class Meta:
        model = User
        fields = UserCreationForm.Meta.fields + ('first_name', 'last_name')
        field_classes = UserCreationForm.Meta.field_classes
