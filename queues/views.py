from copy import copy
from datetime import date, datetime, time
import random
from typing import Optional, Tuple
from uuid import uuid4
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.http import Http404, HttpRequest, HttpResponseForbidden, JsonResponse
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.mixins import LoginRequiredMixin, AccessMixin, UserPassesTestMixin
from django.contrib import messages
from django.views.generic import DetailView, CreateView, UpdateView
from django.forms.models import modelform_factory
from django.utils import timezone
from django.db import connection

from users.models import User

from .forms import MessageForm, QueueRangeExceptionForm, ScheduleForm, AddAdminForm, ExistingUserForm, BookQueueForm
from .models import WEEKDAY_NAMES, JoinMode, QQueue, QueueOpenException, QueueUser, QueueUserRole, Ticket, TicketState, UserQueueReport

def format_time(t: time) -> str:
    return t.strftime('%H:%M')

def format_time_range(t: Optional[Tuple[time, time]]) -> Optional[Tuple[str, str]]:
    return (format_time(t[0]), format_time(t[1])) if t is not None else None

class QueueVisibleMixin(UserPassesTestMixin):
    def test_func(self):
        return self.get_object().is_visible_by(self.request.user)

class QueueOwnerMixin(AccessMixin):
    def dispatch(self, request: HttpRequest, *args, **kwargs):
        if not self.get_object().get_user_role(request.user) == QueueUserRole.OWNER:
            return self.handle_no_permission()
        return super().dispatch(request, *args, **kwargs)

class ModelFormWidgetMixin:
    def get_form_class(self):
        return modelform_factory(self.model, fields=self.fields, widgets=getattr(self, 'widgets', None), labels=getattr(self, 'labels', None))


def suggest_queue(request: HttpRequest) -> Optional[Tuple[str, QQueue]]:
    user = request.user

    state = None

    if user.is_authenticated:
        friend_queues = QQueue.objects.filter(join_mode__in=[JoinMode.PUBLIC, JoinMode.FRIENDS_ONLY], is_privacy_hidden=False)\
                .filter(tickets__friends__id__exact=user.id)\
                .distinct()
        friend_queues = list(filter(lambda x: x.is_visible_by(user), friend_queues))

        if friend_queues:
            choice = random.choice(friend_queues)
            state = 'friends_are_using'

    if state is None:
        queryset = QQueue.objects.filter(join_mode=JoinMode.PUBLIC)
        try:
            choice = random.choice(queryset)
            state = 'discover'
        except:
            pass  # There are no public queues
    return (state, choice) if state is not None else None


@login_required
def list_my_queues(request: HttpRequest):
    queues = request.user.queues.all()
    used_recently = QQueue.objects.filter(tickets__id__exact=request.user.id).distinct()

    ctx = {
        'queues': queues,
        'used_recently': used_recently,
    }
    return render(request, 'queues/list.html', context=ctx)

def queue_search(request: HttpRequest):
    query = request.GET.get('q') or ''
    if query != '':
        result = list(QQueue.objects.filter(name__contains=query).exclude(join_mode=JoinMode.URL_ONLY))
        result = list(filter(lambda x: x.join_mode != JoinMode.URL_ONLY and x.is_visible_by(request.user), result))
    else:
        result = []

    return render(request, 'queues/search.html', context={
        'result': result,
        'query': query,
        'disable_search': True,
    })


class QueueDetailView(QueueVisibleMixin, DetailView):
    model = QQueue
    template_name = "queues/detail.html"

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        queue = data['object']

        raw_schedule = {x.day: [x.from_time, x.to_time] for x in queue.schedule.all()}
        schedule = []
        for i, (_, awesome_name) in enumerate(WEEKDAY_NAMES):
            x = raw_schedule.get(i)
            schedule.append({
                'name': awesome_name,
                'times': format_time_range(x),
            })
        data['schedule'] = schedule
        today_range = queue.get_open_range(date.today())
        if today_range is None:
            data['today_range'] = 'Closed'
        else:
            today_range = format_time_range(today_range)
            data['today_range'] = today_range[0] + ' to ' + today_range[1]

        role = 'none'
        if self.request.user.is_authenticated:
            entry = self.request.user.queues_set.filter(queue=queue).first()
            if entry is not None:
                role = entry.role

            if not queue.is_privacy_hidden:
                friends = queue.tickets.filter(friends__id__exact=self.request.user.id).distinct()
                friend_count = friends.count()
                data['friends'] = [friends[i] for i in random.sample(range(friend_count), min(2, friend_count))]

        ett = round(queue.expected_time_per_ticket)
        if ett > 60*60:
            ett = f'{ett//60*60}h{(ett//60)%60}m'
        elif ett > 60:
            ett = f'{ett//60}m{ett%60}s'
        elif ett > 0:
            ett = f'{ett%60}s'
        else:
            ett = 'none'

        data['expected_time'] = ett
        data['tickets_served'] = queue.ticket_stats_count
        data['can_book'] = queue.can_user_book(self.request.user) and self.request.user.is_authenticated
        data['role'] = role
        return data

class QueueCreateView(ModelFormWidgetMixin, LoginRequiredMixin, CreateView):
    model = QQueue
    fields = ['name', 'description', 'tz', 'image', 'is_privacy_hidden', 'join_mode', 'fixed_ticket_time_minutes']
    template_name = "queues/create.html"
    labels = {
        'fixed_ticket_time_minutes': 'Fixed time per ticket in minutes (leave blank if not needed)'
    }

    def get_form(self, *args, **kwargs):
        form = super().get_form(*args, **kwargs)
        form.fields['tz'].initial = self.request.user.tz
        return form

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        if self.request.method == 'GET' and 'name' in self.request.GET:
            kwargs['initial']['name'] = self.request.GET['name']
        return kwargs

    def form_valid(self, form):
        res = super().form_valid(form)
        self.object.users.add(self.request.user)
        return res

    def get_success_url(self):
        return reverse('queues:queue_details', args=[self.object.pk])

class QueueUpdateView(ModelFormWidgetMixin, LoginRequiredMixin, UpdateView):
    model = QQueue
    fields = ['name', 'description', 'tz', 'image', 'join_mode', 'fixed_ticket_time_minutes']
    template_name = "queues/edit.html"
    labels = {
        'fixed_ticket_time_minutes': 'Fixed time per ticket in minutes (leave blank if not needed)'
    }

    def get_success_url(self):
        return reverse('queues:queue_details', args=[self.object.pk])

    def dispatch(self, request, *args, pk, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        queue = get_object_or_404(QQueue, id=pk)
        uset = queue.users_set.filter(user=request.user).first()
        if uset is None or uset.role != QueueUserRole.OWNER:
            return self.handle_no_permission()
        return super().dispatch(request, *args, **kwargs)


def queue_edit_schedule(request: HttpRequest, pk: uuid4):
    queue = get_object_or_404(QQueue, id=pk)

    if queue.get_user_role(request.user) != QueueUserRole.OWNER:
        return HttpResponseForbidden()

    if request.method == 'POST':
        form = ScheduleForm(request.POST, instance=queue)

        if form.is_valid():
            form.save()
            return redirect(reverse('queues:queue_details', args=[pk]))
    else:
        form = ScheduleForm(instance=queue)

    return render(request, 'queues/edit_schedule.html', {'form': form})

def queue_edit_admins(request: HttpRequest, pk: uuid4):
    queue = get_object_or_404(QQueue, id=pk)

    if queue.get_user_role(request.user) not in [QueueUserRole.OWNER, QueueUserRole.EMPLOYEE]:
        raise Http404()

    user_role = queue.get_user_role(request.user)
    admins = queue.users_set.exclude(role=QueueUserRole.INVITED)

    return render(request, 'queues/admins.html', {
        'queue': queue,
        'user_role': user_role,
        'admins': admins,
    })

def queue_remove_admin(request: HttpRequest, pk: uuid4, user: int):
    queue = get_object_or_404(QQueue, id=pk)
    user = get_object_or_404(User, id=user)

    if queue.get_user_role(request.user) != QueueUserRole.OWNER:
        raise Http404()

    if queue.get_user_role(user) not in [QueueUserRole.OWNER, QueueUserRole.EMPLOYEE]:
        return redirect(reverse('queues:queue_edit_admins', args=[pk]))

    if request.method == 'POST':
        queue.users_set.filter(user=user).delete()
        return redirect(reverse('queues:queue_edit_admins', args=[pk]))

    return render(request, 'queues/admin_remove.html', context={
        'other': user,
        'queue': queue,
    })

def queue_add_admin(request: HttpRequest, pk: uuid4):
    queue = get_object_or_404(QQueue, id=pk)

    if queue.get_user_role(request.user) != QueueUserRole.OWNER:
        raise Http404()

    if request.method == 'POST':
        form = AddAdminForm(request.POST)
        if form.is_valid():
            queue.users_set.filter(user=form.cleaned_data['user']).delete()
            QueueUser(
                queue=queue,
                user=form.cleaned_data['user'],
                role=form.cleaned_data['role'],
            ).save()
            return redirect(reverse('queues:queue_edit_admins', args=[pk]))
    else:
        form = AddAdminForm()

    return render(request, 'queues/admin_add.html', context={
        'queue': queue,
        'form': form,
    })

def queue_leave(request: HttpRequest, pk: uuid4):
    queue = get_object_or_404(QQueue, id=pk)

    if queue.get_user_role(request.user) is None:
        raise Http404()

    if request.method == 'POST':
        queue.users_set.filter(user=request.user).delete()
        return redirect(reverse('queues:queue_list'))

    return render(request, 'queues/leave.html', context={'queue': queue})

def queue_invite(request: HttpRequest, pk: uuid4):
    queue = get_object_or_404(QQueue, id=pk)

    if queue.get_user_role(request.user) not in [QueueUserRole.OWNER, QueueUserRole.EMPLOYEE]:
        raise Http404()

    if queue.join_mode != JoinMode.INVITE:
        return redirect(reverse('queue:details', args=[pk]))

    if request.method == 'POST':
        form = ExistingUserForm(request.POST)
        if form.is_valid():
            role = queue.get_user_role(form.cleaned_data['user'])
            if role == QueueUserRole.INVITED:
                form.add_error('username', 'User already invited')
            elif role is not None:
                form.add_error('username', 'User is admin')
            else:
                QueueUser(
                    queue=queue,
                    user=form.cleaned_data['user'],
                    role=QueueUserRole.INVITED,
                ).save()
                return redirect(reverse('queues:queue_details', args=[pk]))

    else:
        form = ExistingUserForm()
    return render(request, 'queues/invite.html', context={ 'queue': queue, 'form': form })


@login_required
def queue_book(request: HttpRequest, pk: uuid4):
    queue = get_object_or_404(QQueue, id=pk)

    if not queue.is_visible_by(request.user):
        return HttpResponseForbidden()

    error = ""

    if request.method == 'POST':
        form = BookQueueForm(request.POST, instance=queue)
        if form.is_valid():
            Ticket(
                queue=queue,
                user=request.user,
                requested_time=form.cleaned_data['time']
            ).save()
            return redirect(reverse('queues:queue_details', args=[pk]))
        else:
            error = '\n'.join(x[0] for x in form.errors.values())


    return render(request, 'queues/book.html', context={
        'queue': queue,
        'error': error,
    })

def api_book_dates(request: HttpRequest, pk: uuid4):
    queue = get_object_or_404(QQueue, id=pk)

    if not queue.is_visible_by(request.user):
        return HttpResponseForbidden()

    day = datetime.strptime(request.GET['day'], '%Y-%m-%d').date()

    bookable = queue.get_bookable_times(day)

    res = {}
    if bookable is None:
        res['state'] = 'closed'
    elif bookable == []:
        res['state'] = 'full'
    elif isinstance(bookable, list):
        res['state'] = 'choose'
        res['choices'] = [format_time_range(x) for x in bookable]
    else:
        res['state'] = 'range'
        res['range'] = format_time_range(bookable)

    return JsonResponse(res)


def queue_invite(request: HttpRequest, pk: uuid4):
    queue = get_object_or_404(QQueue, id=pk)

    if queue.get_user_role(request.user) not in [QueueUserRole.OWNER, QueueUserRole.EMPLOYEE]:
        raise Http404()

    if request.method == 'POST':
        form = ExistingUserForm(request.POST)
        if form.is_valid():
            user = queue.users_set.filter(user=user).first()
            if user is not None:
                form.add_error('username', 'Already invited')
            else:
                QueueUser(
                    queue=queue,
                    user=form.cleaned_data['user'],
                    role=QueueUserRole.INVITED,
                ).save()
                return redirect(reverse('queues:queue_details', args=[pk]))
    else:
        form = ExistingUserForm()

    return render(request, 'queues/invite.html', context={
        'queue': queue,
        'form': form,
    })

def queue_manage(request: HttpRequest, pk: uuid4):
    queue = get_object_or_404(QQueue, id=pk)

    user_role = queue.get_user_role(request.user)
    if user_role not in [QueueUserRole.OWNER, QueueUserRole.EMPLOYEE]:
        raise Http404()

    now = timezone.localtime()
    open_range = queue.get_open_range(now.date())

    if open_range is None:
        state = 'never_open'
    elif datetime.combine(now.date(), open_range[0], queue.tz) > now:
        state = 'not_open_yet'
    elif datetime.combine(now.date(), open_range[1], queue.tz) < now:
        state = 'closed'
    else:
        state = 'open'

    tickets = queue.tickets_set.filter(state=TicketState.OPEN, requested_time__date=now.date()).order_by('requested_time')
    tickets = [copy(t) for t in tickets]
    for t in tickets:
        t.time = 'No time' if t.requested_time.time() == time(0) else format_time(t.requested_time.astimezone(queue.tz))

    return render(request, 'queues/manage.html', context={
        'queue': queue,
        'tickets': tickets,
        'state': state,
        'open_range': format_time_range(open_range),
        'user_role': user_role,
    })

def queue_manage_serve(request: HttpRequest, pk: uuid4, ticket: int):
    queue = get_object_or_404(QQueue, id=pk)

    user_role = queue.get_user_role(request.user)
    if user_role not in [QueueUserRole.OWNER, QueueUserRole.EMPLOYEE]:
        raise Http404()

    ticket = get_object_or_404(Ticket, id=ticket)
    if ticket.state != TicketState.OPEN:
        return redirect(reverse('queues:queue_manage', args=[pk]))

    if request.method == 'POST':
        ticket.serve()
        return redirect(reverse('queues:queue_manage', args=[pk]))
    return render(request, 'queues/manage_serve.html', context={
        'ticket': ticket,
    })

def queue_manage_cancel(request: HttpRequest, pk: uuid4, ticket: int):
    queue = get_object_or_404(QQueue, id=pk)

    user_role = queue.get_user_role(request.user)
    if user_role not in [QueueUserRole.OWNER, QueueUserRole.EMPLOYEE]:
        raise Http404()

    ticket = get_object_or_404(Ticket, id=ticket)

    if ticket.state != TicketState.OPEN:
        return redirect(reverse('queues:queue_manage', args=[pk]))

    if request.method == 'POST':
        form = MessageForm(request.POST)

        if form.is_valid():
            mex = form.cleaned_data['message']
            ticket.cancel('queue', mex)
            return redirect(reverse('queues:queue_manage', args=[pk]))
    else:
        form = MessageForm()

    return render(request, 'queues/manage_cancel.html', context={
        'ticket': ticket,
        'form': form,
    })

def queue_manage_exception(request: HttpRequest, pk: uuid4):
    queue = get_object_or_404(QQueue, id=pk)

    user_role = queue.get_user_role(request.user)
    if user_role != QueueUserRole.OWNER:
        raise Http404()

    now = timezone.localtime()
    has_exception = queue.exc_schedule.filter(day=now.date()).count() > 0

    if request.method == 'POST':
        form = QueueRangeExceptionForm(request.POST, queue=queue)
        if form.is_valid():
            queue.exc_schedule.filter(day=now.date()).delete()
            if form.cleaned_data['keep_closed']:
                from_time, to_time = None, None
            else:
                from_time = form.cleaned_data['from_time']
                to_time = form.cleaned_data['to_time']
            QueueOpenException(
                queue=queue,
                day=now.date(),
                from_time=from_time,
                to_time=to_time,
            ).save()
            return redirect(reverse('queues:queue_manage', args=[pk]))
    else:
        form = QueueRangeExceptionForm(queue=queue)

    return render(request, 'queues/manage_exception.html', context={
        'queue': queue,
        'form': form,
        'has_exception': has_exception,
    })

@login_required
def queue_report(request: HttpRequest, pk: uuid4):
    queue = get_object_or_404(QQueue, id=pk)

    if not queue.is_visible_by(request.user):
        raise Http404()

    if request.method == 'POST':
        form = MessageForm(request.POST)
        if form.is_valid():
            UserQueueReport(
                user=request.user,
                queue=queue,
                reason=form.cleaned_data['message'],
            ).save()
            messages.success(request, "Your report will be reviewed shortly", "Success")
            return redirect(reverse('queues:queue_details', args=[pk]))
    else:
        form = MessageForm()

    return render(request, 'queues/report.html', context={
        'queue': queue,
        'form': form,
    })

@permission_required('queues.manage_reports')
def queue_report_review(request: HttpRequest, pk: uuid4):
    queue = get_object_or_404(QQueue, id=pk)

    if request.method == 'POST':
        n = queue.reports_set.filter(reviewed=False).update(reviewed=True)
        messages.success(request, f'{n} reports reviewed!')
        return redirect(reverse('queues:report_list'))

    reports = queue.reports_set.filter(reviewed=False).all()

    return render(request, 'queues/report_details.html', context={
        'queue': queue,
        'reports': reports,
    })




@permission_required('queues.manage_reports')
def report_list(request: HttpRequest):
    queues = []

    with connection.cursor() as cursor:
        cursor.execute('select queue_id, count(*) as cnt from queues_userqueuereport where not reviewed group by queue_id order by cnt desc')
        res = cursor.fetchall()
        for row in res:
            queues.append((get_object_or_404(QQueue, id=row[0]), row[1]))

    return render(request, 'queues/report_list.html', context={
        'reports': queues,
    })



@login_required
def list_my_tickets(request: HttpRequest):
    tickets = request.user.tickets_set.all().order_by('-requested_time')

    # Shallow copy!
    tickets = [copy(t) for t in tickets]
    for t in tickets:
        t.time = t.requested_time.astimezone(request.user.tz).strftime('%Y-%m-%d %H:%M')
        t.card_style = ''
        if t.state == TicketState.SERVED:
            t.card_style = 'text-white bg-secondary'
        if t.state in (TicketState.QUEUE_CANCELLED, TicketState.USER_CANCELLED):
            t.card_style = 'bg-warning'

    ctx = {
        'tickets': tickets
    }
    return render(request, 'tickets/list.html', context=ctx)

@login_required
def ticket_details(request: HttpRequest, pk: int):
    ticket = get_object_or_404(Ticket, id=pk)

    if not (request.user.is_superuser or request.user == ticket.user):
        return HttpResponseForbidden()

    return render(request, 'tickets/detail.html', context={
        'object': ticket,
        'time': ticket.requested_time.astimezone(request.user.tz).strftime('%Y-%m-%d %H:%M'),
    })

@login_required
def ticket_cancel(request: HttpRequest, pk: int):
    ticket = get_object_or_404(Ticket, id=pk)

    if request.user != ticket.user:
        return HttpResponseForbidden()

    if request.method == 'POST':
        form = MessageForm(request.POST)

        if form.is_valid():
            mex = form.cleaned_data['message']
            ticket.cancel('user', mex)
            return redirect(reverse('queues:ticket_list'))
    else:
        form = MessageForm()


    return render(request, 'tickets/cancel.html', context={
        'ticket': ticket,
        'time': ticket.requested_time.astimezone(request.user.tz).strftime('%Y-%m-%d %H:%M'),
        'form': form,
    })
