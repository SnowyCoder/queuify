from copy import copy
from django.http import Http404, HttpRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.views.generic import DetailView, CreateView, UpdateView
from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView
from django.contrib import messages
from django.utils import timezone
from django.db.models import Q



from .forms import EditUserForm, CreateUserForm
from .models import User

class CustomLoginView(LoginView):
    def form_valid(self, form):
        user = form.get_user()
        messages.success(self.request, "Login successful, welcome!", f"Welcome {user.first_name}!")
        return super().form_valid(form)


class UserDetailView(DetailView):
    template_name = 'user/user_detail.html'
    model = User
    context_object_name = 'quser'

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        me = self.request.user
        user = data['object']
        friend_status = 'unauthenticated'
        if self.request.user.is_authenticated:
            if user == me:
                friend_status = 'me'
                data['friend_count'] = user.friends.count()
                data['local_time'] = timezone.localtime().strftime('%H:%M')
            elif user in me.friends.all():
                friend_status = 'friend'
            elif user in me.friend_requests.all():
                friend_status = 'request_sent'
            elif user in me.received_friend_requests.all():
                friend_status = 'request_received'
            elif user.is_authenticated:
                friend_status = 'not_friend'
        data['friend_status'] = friend_status
        return data


class UserEditView(UpdateView, LoginRequiredMixin):
    template_name = 'user/user_edit.html'
    model = User
    form_class = EditUserForm

    def get_object(self):
        return self.request.user

    def get_success_url(self):
        return reverse('users:profile', kwargs={'pk': self.object.pk})


class UserCreateView(CreateView):
    form_class = CreateUserForm
    template_name = "user/user_create.html"
    success_url = reverse_lazy("users:login")

    def form_valid(self, form):
        self.object = form.save()
        username = self.request.POST['username']
        password = self.request.POST['password1']
        # Automatic authentication and login
        user = authenticate(username=username, password=password)
        login(self.request, user)
        # Redirect user to their profile to finish user creation
        messages.success(self.request, "Congrats! Do you want to receive notifications?", f"Welcome {user.first_name}")
        return redirect(reverse('users:profile', kwargs={'pk': user.id}))

def search(request: HttpRequest):
    query = request.GET.get('q') or ''
    if query != '':
        result = list(User.objects.filter(Q(username__contains=query) | Q(first_name__contains=query) | Q(last_name__contains=query)))
    else:
        result = []

    result = [copy(r) for r in result]
    for r in result:
        r.state = 'none'
        if not request.user.is_authenticated:
            continue
        if r == request.user:
            r.state = 'you'
        elif r in request.user.friends.all():
            r.state = 'friend'

    return render(request, 'user/search.html', context={
        'result': result,
        'query': query,
    })

@login_required
def user_self(request: HttpRequest):
    return redirect(reverse('users:profile', kwargs={'pk': request.user.id}))

@login_required
def forget(request: HttpRequest):
    if request.method == 'GET':
        return render(request, 'user/user_forget.html')
    elif request.method == 'POST':
        request.user.delete()
        return redirect(reverse('home'))

@login_required
def friends(request: HttpRequest):
    user = request.user
    ctx = {
        'friends': user.friends.all(),
        'friend_requests': user.friend_requests.all(),
        'received_friend_requests': user.received_friend_requests.all(),
    }
    return render(request, 'user/friends.html', context=ctx)


@login_required
def remove_friend(request: HttpRequest, ifriend: int):
    friend = get_object_or_404(User, id=ifriend)

    user = request.user
    is_friend = friend in user.friends.all()
    if not (is_friend or (friend in user.friend_requests.all())):
        raise Http404(
            f"{friend.username} is not your friend"
        )

    if request.method == 'GET':
        ctx = {
            'friend': friend,
            'status': 'friend' if is_friend else 'sent',
        }
        return render(request, 'user/friend_delete.html', context=ctx)
    elif request.method == 'POST':
        if is_friend:
            user.friends.remove(friend)
            friend.friends.remove(user)
            messages.success(request, f"{friend.first_name} is no longer your friend", "Success")
        else:
            user.friend_requests.remove(friend)
            messages.success(request, f"{friend.first_name} friend request removed", "Success")
        return redirect(reverse('users:friends'))

@login_required
def reject_friend(request: HttpRequest, ifriend: int):
    friend = get_object_or_404(User, id=ifriend)

    user = request.user
    if friend not in user.received_friend_requests.all():
        messages.error(request, f"{user.first_name} is not your friend", "Error")
        return redirect(reverse('users:friends'))

    if request.method == 'GET':
        ctx = {
            'friend': friend,
            'status': 'received',
        }
        return render(request, 'user/friend_delete.html', context=ctx)
    elif request.method == 'POST':
        user.received_friend_requests.remove(friend)
        messages.success(request, f"{friend.first_name} friendship rejected", "Success")
        return redirect(reverse('users:friends'))

@login_required
def add_friend(request: HttpRequest, iother: int):
    user = request.user
    other = get_object_or_404(User, id=iother)

    if other in user.friends.all() or (other in user.friend_requests.all()) or user.id == iother:
        # User is already a friend, or
        # Request already made, we cannot make two requests or
        # user is me
        messages.warning(request, f"You cannot request {other.first_name}'s friendship", "Error")
        return redirect(reverse('users:friends'))

    is_confirmation = False
    if user in other.friend_requests.all():
        if request.method == 'POST':
            # Friendship accepted :3
            other.friend_requests.remove(user)
            user.friends.add(other)
            other.friends.add(user)
            messages.error(request, "Friendship accepted!", "Success!")
            return redirect(reverse('users:friends'))
        else:
            is_confirmation = True

    if request.method == 'POST':
        user.friend_requests.add(other)
        messages.success(request, "Friend request sent!", "Sent!")
        return redirect(reverse('users:friends'))
    else:
        ctx = {
            'is_confirmation': is_confirmation
        }
        return render(request, "user/friend_request.html", context=ctx)

@login_required
def notification_subscribe(request: HttpRequest):
    if request.method != 'POST':
        raise Http404()

    request.user.notification_subscription = request.body.decode('utf-8')
    request.user.save()
    return JsonResponse({
        'state': 'ok',
    })
