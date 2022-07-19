
from django.urls import path
from django.contrib.auth.views import LogoutView
from . import views as v

app_name = "users"

urlpatterns = [
    path("profile/", v.user_self, name="view_self"),
    path("profile/<int:pk>", v.UserDetailView.as_view(), name="profile"),
    path("profile_edit/", v.UserEditView.as_view(), name="edit_profile"),
    path("forget/", v.forget, name="forget"),

    path("register/", v.UserCreateView.as_view(), name="register"),
    path("login/", v.CustomLoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),

    path('friends/', v.friends, name='friends'),
    path('friends/add/<int:iother>', v.add_friend, name='add_friend'), # Also used to accept requests
    path('friends/remove/<int:ifriend>', v.remove_friend, name='remove_friend'), # Also used to remove friend requests
    path('friends/reject/<int:ifriend>', v.reject_friend, name='reject_friend'), # Reject received friend request

    path('search/', v.search, name='search'),
    path('notification_subscribe/', v.notification_subscribe, name='notification_subscribe')
]
