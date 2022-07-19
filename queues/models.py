from datetime import date, datetime, time, timedelta
from typing import List, Optional, Tuple, Union
import uuid
from django.core.validators import MaxValueValidator
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.urls import reverse
from timezone_field import TimeZoneField
from webpush import send_user_notification

from users.models import User

WEEKDAY_NAMES = [
    ('monday', _('Monday')),
    ('tuesday', _('Tuesday')),
    ('wednesday', _('Wednesday')),
    ('thursday', _('Thursday')),
    ('friday', _('Friday')),
    ('saturday', _('Saturday')),
    ('sunday', _('Sunday')),
]

# For how many iteration the filter should use an average
FILTER_BOOTSTRAP_ITERATIONS = 10
# How much the filter favours the memory instead of the new measure
# should be between 0 and 1 (0=filter uses just the new measure, 1 = filter only uses memory)
FILTER_MEMORY = 0.8


def time_to_secs(x: time) -> int:
    return (x.hour * 60 + x.minute) * 60 + x.second

def secs_to_time(x: int) -> time:
    return time(x // (60 * 60), (x // 60) % 60, x % 60)


class QueueOpenRange(models.Model):
    queue = models.ForeignKey('QQueue', verbose_name=_("queue"), related_name="schedule", on_delete=models.CASCADE)
    day = models.PositiveSmallIntegerField(verbose_name=_("day"), validators=[MaxValueValidator(7)])
    from_time = models.TimeField(verbose_name=_("from"))
    to_time = models.TimeField(verbose_name=_("to"))

    class Meta:
        verbose_name = _("Opening range")
        verbose_name_plural = _("Opening ranges")

    def __str__(self):
        day_name = WEEKDAY_NAMES[self.day][1]
        return f"{day_name} {self.from_time} to {self.to_time}"

    def is_open_at(self, time: time) -> bool:
        return self.from_time < time < self.to_time

class QueueOpenException(models.Model):
    queue = models.ForeignKey('QQueue', verbose_name=_("queue"), related_name="exc_schedule", on_delete=models.CASCADE)
    day = models.DateField(verbose_name=_("day"))
    from_time = models.TimeField(verbose_name=_("from"), null=True)
    to_time = models.TimeField(verbose_name=_("to"), null=True)

    class Meta:
        verbose_name = _("Opening range exception")
        verbose_name_plural = _("Opening range exceptions")

    def __str__(self):
        return f"{self.day} {self.from_time} to {self.to_time}"

    def is_open_at(self, time: time) -> bool:
        if self.from_time is None:
            return False
        return self.from_time < time < self.to_time


class JoinMode(models.TextChoices):
    PUBLIC = 'PUB', _('Public')
    URL_ONLY = 'URL', _('URL only')
    FRIENDS_ONLY = 'FRI', _('Friends only')
    INVITE = 'INV', _('Invite only')


class QQueue(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(_("Name"), max_length=50)
    description = models.CharField(_("Description"), max_length=1024, default="")
    # Queue needs a timezone too, datetimes (like schedules) should be specified using this timezone
    tz = TimeZoneField(default="Europe/Rome", choices_display="WITH_GMT_OFFSET")
    image = models.ImageField(_("Image"), null = True, blank=True)
    is_privacy_hidden = models.BooleanField(_("Privacy hidden"), default=False)

    join_mode = models.CharField(
        max_length=3,
        choices=JoinMode.choices,
        default=JoinMode.INVITE,
    )

    expected_time_per_ticket = models.FloatField(_('Expected time per ticket'), default=0)
    # Number of tickets used to estimate expected_time_per_ticket
    ticket_stats_count = models.IntegerField(_("Ticket status count"), default=0)
    fixed_ticket_time_minutes = models.IntegerField(_("Fixed ticket time (minutes)"), default=None, null=True, blank=True)

    users = models.ManyToManyField(User, through='QueueUser', verbose_name=_("users"), related_name="queues")
    tickets = models.ManyToManyField(User, through='Ticket', verbose_name=_("tickets"), related_name="tickets")
    reports = models.ManyToManyField(User, through='UserQueueReport', verbose_name=_("reports"), related_name="reported_queues")

    class Meta:
        verbose_name = _("Queue")
        verbose_name_plural = _("Queues")

    def __str__(self) -> str:
        return f"{self.name} ({self.join_mode})"

    def is_open_at(self, dt: datetime) -> bool:
        exception = self.exc_schedule.filter(day=dt.date()).first()

        if exception is not None:
            return exception.is_open_at(dt.time())

        day_range = self.schedule.filter(day=dt.weekday()).first()

        return day_range is not None and day_range.is_open_at(dt.time())

    def get_user_role(self, user: User) -> Optional['QueueUserRole']:
        if not user.is_authenticated:
            return None
        uset = self.users_set.filter(user=user).first()
        return None if uset is None else uset.role

    def is_visible_by(self, user: User) -> bool:
        if user.has_perm('queues.manage_reports'):
            return True
        return self.can_user_book(user)

    def can_user_book(self, user: User) -> bool:
        if self.join_mode == JoinMode.INVITE:
            return self.get_user_role(user) is not None
        if self.join_mode == JoinMode.FRIENDS_ONLY:
            if not user.is_authenticated:
                return False
            if self.get_user_role(user) in [QueueUserRole.OWNER, QueueUserRole.EMPLOYEE]:
                return True
            return self.users_set\
                    .exclude(role=QueueUserRole.INVITED)\
                    .filter(user__friends__id__exact=user.id)\
                    .count() > 0

        return True

    def get_open_range(self, day: date) -> Optional[Tuple[time, time]]:
        exception = self.exc_schedule.filter(day=day).first()
        if exception is not None:
            return (exception.from_time, exception.to_time) if exception.from_time is not None else None

        schedule = self.schedule.filter(day=day.weekday()).first()
        if schedule is None:
            return None
        return (schedule.from_time, schedule.to_time)

    def on_wait_time(self, wait_time_secs: int, commit: bool=True):
        # Use average for the first 10 values, and use a very very simple statistical filter
        # afterwards (I'm not a statistician, but it seems quite pretty)
        ett = self.expected_time_per_ticket
        count = self.ticket_stats_count

        if count < FILTER_BOOTSTRAP_ITERATIONS:
            ett = (ett * count + wait_time_secs) / (count + 1)
        else:
            # Linear interpolation between memory and new measure
            ett = ett * FILTER_MEMORY + (1 - FILTER_MEMORY) * wait_time_secs

        self.expected_time_per_ticket = ett
        self.ticket_stats_count = count + 1

        if commit:
            self.save()

    def get_bookable_times(self, day: date, now: Optional[datetime]=None) -> None | Tuple[time, time] | List[Tuple[time, time]]:
        if now is None:
            now = datetime.now(tz=self.tz)

        if datetime.combine(day, time.max, self.tz) < now:
            return None # Can't book in the past

        open_range = self.get_open_range(day)
        if open_range is None:
            return None
        ticket_secs = self.fixed_ticket_time_minutes
        if ticket_secs is None:
            # There's no fixed ticket time, you can use any time between x and y
            # (any time in the future!)
            open_range = (secs_to_time(max(time_to_secs(open_range[0]), time_to_secs(now.time()))), open_range[1])
            return open_range
        ticket_secs = ticket_secs * 60
        # Split time in ranges of self.fixed_ticket_time_minutes
        # Obviously python time does not support any kind of arithmetic operations...
        start_time = time_to_secs(open_range[0])
        end_time = time_to_secs(open_range[1])
        itime = start_time

        tickets = list(self.tickets_set.filter(requested_time__date=day, state=TicketState.OPEN).order_by('requested_time'))
        iticket = 0

        def time_to_local(t: time) -> time:
            return datetime.combine(day, t, self.tz).astimezone(timezone.get_current_timezone()).time()

        res = []
        while itime < end_time:
            current = secs_to_time(itime)

            if day == now.date() and datetime.combine(day, current, self.tz) < now:
                itime += ticket_secs
                continue

            while iticket < len(tickets) and time_to_secs(tickets[iticket].requested_time.astimezone(self.tz).time()) <= itime - ticket_secs:
                iticket += 1

            is_time_used = iticket < len(tickets) and (itime <= time_to_secs(tickets[iticket].requested_time.astimezone(self.tz).time()) < itime + ticket_secs)
            if not is_time_used:
                res.append((
                    time_to_local(current),
                    time_to_local(secs_to_time(min(itime + ticket_secs, end_time)))
                ))
            else:
                iticket += 1

            itime += ticket_secs
        return res


class QueueUserRole(models.TextChoices):
    # Owner of the queue, can do anything
    OWNER = 'OWN', _('owner')
    # Can only manage tickets
    EMPLOYEE = 'EMP', _('employee')
    # Can only subscribe to tickets
    INVITED = 'INV', _('invited')


class QueueUser(models.Model):
    queue = models.ForeignKey(QQueue, verbose_name=_("queue"), related_name="users_set", on_delete=models.CASCADE)
    user = models.ForeignKey(User, verbose_name=_("user"), related_name="queues_set", on_delete=models.CASCADE)
    role = models.CharField(
        max_length=3,
        choices=QueueUserRole.choices,
        default=QueueUserRole.OWNER,
    )


class TicketState(models.TextChoices):
    OPEN = 'OPE', _('Open')
    # Cancelled by user
    USER_CANCELLED = 'UCA', _('Cancelled by the user')
    # Cancelled by a queue operator
    QUEUE_CANCELLED = 'QCA', _('Cancelled by a queue operator')
    # Served correctly
    SERVED = 'SER', _('Served')


class Ticket(models.Model):
    queue = models.ForeignKey(QQueue, verbose_name=_("queue"), related_name="tickets_set", on_delete=models.CASCADE)
    user = models.ForeignKey(User, verbose_name=_("user"),  related_name="tickets_set", on_delete=models.CASCADE)

    creation_time = models.DateTimeField(verbose_name=_("Creation date"), auto_now_add=True)
    requested_time = models.DateTimeField(verbose_name=_("Requested time"))

    state = models.CharField(
        max_length=3,
        choices=TicketState.choices,
        default=TicketState.OPEN,
    )

    closure_time = models.DateTimeField(verbose_name=_("Closure time"), default=None, null=True)
    wait_time_secs = models.IntegerField(verbose_name=_("Wait time"), default=None, null=True)
    cancel_message = models.CharField(verbose_name=_("Closure message"), max_length=128, default=None, null=True)

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._is_cleaned = False

    @transaction.atomic
    def serve(self, commit: bool=True, now: Optional[datetime]=None):
        if self.state != TicketState.OPEN:
            raise Exception("Invalid ticket state")

        if now is None:
            now = timezone.now()
        self.state = TicketState.SERVED
        self.closure_time = now

        fromt = None
        if self.requested_time is not None:
            fromt = self.requested_time
        elif open_time := self.queue.get_open_time(now.date()):
            fromt = max(open_time, self.creation_time)

        if fromt is None:
            self.wait_time_secs = None
            self.save()
            self.try_check_next_notification()
            return

        if fromt > now:
            self.wait_time_secs = 0
        else:
            diff = now - fromt
            assert(diff.days <= 0)
            self.wait_time_secs = diff.seconds

        # Update statistics
        self.queue.on_wait_time(self.wait_time_secs)
        if commit:
            self.save()
        self.try_check_next_notification()

    def cancel(self, by_whom: Union['user', 'queue'], message: str, commit: bool=True, now: Optional[datetime]=None):
        if self.state != TicketState.OPEN:
            raise Exception("Invalid ticket state")

        if now is None:
            now = timezone.now()
        self.state = TicketState.USER_CANCELLED if by_whom == 'user' else TicketState.QUEUE_CANCELLED
        self.closure_time = now
        self.cancel_message = message
        if commit:
            self.save()
        self.try_check_next_notification()

    def try_check_next_notification(self):
        next_ticket = self.queue.tickets_set\
            .filter(requested_time__date=date.today(), state=TicketState.OPEN)\
            .order_by('requested_time')\
            .first()
        # Send ticket to the next in the queue
        if next_ticket is not None:
            payload = {
                'head': f'Go to {next_ticket.queue.name}',
                'body': f'Queue {next_ticket.queue.name} is free!',
                'url': reverse('queues:ticket_details', args=[next_ticket.id]),
            }
            send_user_notification(user=next_ticket.user, payload=payload, ttl=1000)


    def clean(self):
        # Check that this ticket does not collide
        if self.state == TicketState.OPEN and self.queue.fixed_ticket_time_minutes is not None:
            open_day = self.queue.get_open_range(self.requested_time.date())
            if (time_to_secs(self.requested_time.time()) - time_to_secs(open_day[0])) % (self.queue.fixed_ticket_time_minutes * 60) != 0:
                raise ValidationError("Ticket time is not aligned to queue's fixed slots")

            # https://stackoverflow.com/questions/100210/what-is-the-standard-way-to-add-n-seconds-to-datetime-time-in-python
            # This seems to be the, uhm, "pythonic" way to add times(?)
            end_time = (datetime.combine(date.today(), self.requested_time.time()) + timedelta(minutes=self.queue.fixed_ticket_time_minutes)).time()
            q = self.queue.tickets_set.filter(
                requested_time__date=self.requested_time.date(),
                requested_time__time__gte=self.requested_time.time(),
                requested_time__time__lt=end_time,
                state=TicketState.OPEN,
            ).first()
            if q is not None and q.id != self.id:
                raise ValidationError("Ticket time slot already booked")
        self._is_cleaned = True

    def save(self):
        if not self._is_cleaned:
            self.clean()
        return super().save()

class UserQueueReport(models.Model):
    queue = models.ForeignKey(QQueue, verbose_name=_("queue"), related_name="reports_set", on_delete=models.CASCADE)
    user = models.ForeignKey(User, verbose_name=_("user"),  related_name="queue_reports_set", on_delete=models.CASCADE)

    creation_time = models.DateTimeField(verbose_name=_("Creation date"), auto_now_add=True)
    reason = models.CharField(verbose_name=_("Reason"), max_length=256)
    reviewed = models.BooleanField(verbose_name=_("Reviewed"), default=False)

    class Meta:
        permissions = [
            ("manage_reports", "Can view and review submitted reports"),
            ("view_all_stats", "Can view stats of queues they do not own"),
        ]
