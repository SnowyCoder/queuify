from datetime import datetime, time
from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Div, HTML
from core.utils import crispy_save_or_go_back

from queues.models import WEEKDAY_NAMES, QQueue, QueueOpenRange, time_to_secs
from users.models import User

class ScheduleForm(forms.Form):
    def __init__(self, *args, instance: QQueue, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance = instance

        fields = []
        schedule = {x.day: [x.from_time, x.to_time] for x in instance.schedule.all()}
        for iday, (name, awesome_name) in enumerate(WEEKDAY_NAMES):
            init = schedule.get(iday, None)
            create_time_field = lambda x: forms.TimeField(initial=x, required=False, widget=forms.TimeInput(format="%H:%M"))
            self.fields[f'day_{name}_from'] = create_time_field(None if init is None else init[0])
            self.fields[f'day_{name}_to'] = create_time_field(None if init is None else init[1])
            fields.append(
                Div(
                    HTML(f'<div class="col">{awesome_name}</div>'),
                    Div(f'day_{name}_from', css_class="col"),
                    Div(f'day_{name}_to', css_class="col"),
                    css_class="row"
                )
            )

        self.helper = FormHelper()
        self.helper.form_show_labels = False
        self.helper.layout = Layout(
            Div(*fields, style="width: 20em"),
            crispy_save_or_go_back()
        )

    def clean(self):
        cleaned_data = super().clean()

        for name, _ in WEEKDAY_NAMES:
            tfrom = cleaned_data.get(f'day_{name}_from')
            tto = cleaned_data.get(f'day_{name}_to')
            if tfrom is not None and tto is not None:
                if tfrom > tto:
                    self.add_error(f'day_{name}_to', 'Invalid time range')
            elif tfrom is not None and tto is None:
                self.add_error(f'day_{name}_to', 'Schedule incomplete')
            elif tfrom is None and tto is not None:
                self.add_error(f'day_{name}_from', 'Schedule incomplete')

    def save(self):
        if self.errors:
            raise ValueError(
                "The %s could not be %s because the data didn't validate."
                % (
                    self.instance._meta.object_name,
                    "created" if self.instance._state.adding else "changed",
                )
            )
        for i, (name, _) in enumerate(WEEKDAY_NAMES):
            queryset = self.instance.schedule.filter(day=i)
            tfrom = self.cleaned_data[f'day_{name}_from']
            tto =  self.cleaned_data[f'day_{name}_to']
            if tfrom is None:
                queryset.delete()
                continue
            day_range = queryset.first()
            if day_range is None:
                day_range = QueueOpenRange(
                    queue=self.instance,
                    day=i,
                    from_time=tfrom,
                    to_time=tto,
                )
            else:
                day_range.from_time = tfrom
                day_range.to_time = tto
            day_range.save()

        return self.instance

class ExistingUserForm(forms.Form):
    username = forms.CharField(label='Username')

    def clean(self):
        cleaned_data = super().clean()
        user = User.objects.filter(username=cleaned_data['username']).first()
        if user is None:
            self.add_error('username', 'Cannot find user')
        cleaned_data['user'] = user
        return cleaned_data

class AddAdminForm(ExistingUserForm):
    role = forms.ChoiceField(label='Role', choices=[('EMP', 'Employee'), ('OWN', 'Owner')])

    field_order = ['username', 'role']

class BookQueueForm(forms.Form):
    day = forms.DateField()

    def __init__(self, data, *args, instance: QQueue, **kwargs) -> None:
        super().__init__(data, *args, **kwargs)
        self._instance = instance

        try:
            day = self.fields['day'].to_python(data.get('day'))
        except ValidationError:
            return

        if instance.fixed_ticket_time_minutes is not None:
            choices = instance.get_bookable_times(day)
            self.fields['time'] = forms.ChoiceField(
                choices = [(x[0].strftime('%H:%M'), f'not used') for x in choices]
            )
        else:
            open_time = instance.get_bookable_times(day)
            def is_in_range(x: time):
                if not (time_to_secs(open_time[0]) <= time_to_secs(x) < time_to_secs(open_time[1])):
                    raise ValidationError(f'time not in open hours ({open_time[0].strftime("%H:%M")}-{open_time[1].strftime("%H:%M")})')

            self.fields['time'] = forms.TimeField(
                required=False,
                validators=[is_in_range]
            )

    def clean(self):
        super().clean()

        if 'time' in self.cleaned_data and self.cleaned_data['time'] is not None:
            time = self.cleaned_data['time']
            time = datetime.strptime(self.cleaned_data['time'], '%H:%M').time() if isinstance(time, str) else time
            self.cleaned_data['time'] = datetime.combine(
                self.cleaned_data['day'],
                time,
                self._instance.tz,
            )
        elif self.is_valid():
            open_h = self._instance.get_open_range(self.cleaned_data['day'])
            self.cleaned_data['time'] = datetime.combine(self.cleaned_data['day'], open_h[0], self._instance.tz)

        return self.cleaned_data

class MessageForm(forms.Form):
    message = forms.CharField()

class QueueRangeExceptionForm(forms.Form):
    from_time = forms.TimeField(widget=forms.TimeInput(format="%H:%M"))
    to_time = forms.TimeField(widget=forms.TimeInput(format="%H:%M"))
    keep_closed = forms.BooleanField(initial=False, required=False)

    def __init__(self, *args, queue: QQueue, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self._queue = queue
        now = datetime.now(queue.tz)
        open_range = queue.get_open_range(now.date())
        if open_range is not None:
            self.fields['from_time'].initial = open_range[0]
            self.fields['to_time'].initial = open_range[1]

            if now > datetime.combine(now.date(), open_range[0], queue.tz):
                self.fields['from_time'].disabled = True
                self.fields['to_time'].initial = now.time()
                self.fields['keep_closed'].widget = forms.HiddenInput()
                self.fields['keep_closed'].disabled = True
            else:
                self.fields['from_time'].initial = now.time()
        else:
            self.fields['from_time'].initial = now.time()
