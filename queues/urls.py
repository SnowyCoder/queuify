
from django.urls import path

from . import views as v
from . import stats_views as sv

app_name = "queues"

urlpatterns = [
    path("queues/", v.list_my_queues, name="queue_list"),
    path("queues/create/", v.QueueCreateView.as_view(), name="queue_create"),

    path("queue/<uuid:pk>/", v.QueueDetailView.as_view(), name="queue_details"),
    path("queue/<uuid:pk>/edit", v.QueueUpdateView.as_view(), name="queue_edit"),
    path("queue/<uuid:pk>/schedule_edit", v.queue_edit_schedule, name="queue_edit_schedule"),
    path("queue/<uuid:pk>/admins", v.queue_edit_admins, name="queue_edit_admins"),
    path("queue/<uuid:pk>/admin_add", v.queue_add_admin, name="queue_add_admin"),
    path("queue/<uuid:pk>/admin_remove/<int:user>", v.queue_remove_admin, name="queue_remove_admin"),
    # Used for admins and invited users to leave their own role
    path("queue/<uuid:pk>/leave", v.queue_leave, name="queue_leave"),
    path("queue/<uuid:pk>/invite", v.queue_invite, name="queue_invite"),

    # Used for the queue owners to manage received tickets
    path("queue/<uuid:pk>/manage", v.queue_manage, name="queue_manage"),
    path("queue/<uuid:pk>/manage/exception", v.queue_manage_exception, name="queue_add_exception"),
    path("queue/<uuid:pk>/manage/serve/<int:ticket>", v.queue_manage_serve, name="queue_manage_serve_ticket"),
    path("queue/<uuid:pk>/manage/cancel/<int:ticket>", v.queue_manage_cancel, name="queue_manage_cancel_ticket"),
    path("queue/<uuid:pk>/book", v.queue_book, name="queue_book"),
    path("queue/<uuid:pk>/book_api", v.api_book_dates, name="queue_book_api"), # AJAX
    path("queue/<uuid:pk>/report", v.queue_report, name="queue_report"),
    path("queue/<uuid:pk>/report_details", v.queue_report_review, name="queue_report_review"),
    path("queue/<uuid:pk>/stats", sv.queue_stats, name="queue_stats"),
    path("queue/<uuid:pk>/stats_api", sv.api_query, name="queue_stats_api"),

    path("reports", v.report_list, name="report_list"),

    path("ticket/", v.list_my_tickets, name="ticket_list"),
    path("ticket/<int:pk>", v.ticket_details, name="ticket_details"),
    path("ticket/<int:pk>/cancel", v.ticket_cancel, name="ticket_cancel"),

    path("search", v.queue_search, name="search")
]
