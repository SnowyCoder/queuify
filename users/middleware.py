from django.http import HttpRequest
from django.utils import timezone


class TimezoneMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest):
        if request.user.is_authenticated:
            timezone.activate(request.user.tz)
        else:
            timezone.deactivate()
        return self.get_response(request)
