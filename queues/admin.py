from django.contrib import admin
from .testdb import init_test
from . import models

admin.site.register([
    models.QQueue,
    models.QueueOpenRange,
    models.QueueOpenException,
    models.QueueUser,
    models.Ticket,
    models.UserQueueReport,
])

init_test()
