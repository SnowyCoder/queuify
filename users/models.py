from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils.translation import gettext_lazy as _
from django.contrib import admin
from timezone_field import TimeZoneField


class User(AbstractUser):
    pronouns = models.CharField(_("Pronouns"), max_length=32, default="they/them")
    description = models.CharField(_("Description"), max_length=1024, null=False, default="")
    image = models.ImageField(_("Image"), null=True, blank=True)
    tz = TimeZoneField(default="Europe/Rome", choices_display="WITH_GMT_OFFSET")

    friends = models.ManyToManyField('User', through='UserFriend', related_name="_unused_friends_related")
    friend_requests = models.ManyToManyField('User', related_name="received_friend_requests")



class UserFriend(models.Model):
    user_from = models.ForeignKey(User, on_delete=models.CASCADE, related_name="_unused_a")
    user_to = models.ForeignKey(User, on_delete=models.CASCADE, related_name="_unused_b")

    def save(self, *args, **kwargs):
        if self.user_from == self.user_to:
            raise Exception("Cannot be friends to yourself")
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user_from} to {self.user_to}"
