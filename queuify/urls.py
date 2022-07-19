"""queuify URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.shortcuts import render
from django.urls import path, include
from django.http import HttpRequest
from django.conf.urls.static import static
from django.views.generic import TemplateView
from queues.views import suggest_queue

from queuify import settings


def home(request: HttpRequest):
    suggested = suggest_queue(request)
    return render(request, template_name="home.html", context={
        'suggested': suggested,
    })


urlpatterns = [
    path('', home, name="home"),
    path('admin/', admin.site.urls),
    path('users/', include('users.urls')),
    path('', include('queues.urls')),
    path('webpush/', include('webpush.urls')),
]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
