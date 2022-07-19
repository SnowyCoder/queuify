from django.contrib import admin

from . import models
from .testdb import init_test

admin.site.register([
    models.User,
    models.UserFriend,
])

init_test()
