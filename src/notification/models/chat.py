from platform import platform
from django.db import models
from django.contrib.postgres.fields import JSONField

from device.models import User


class UserChatContext(models.Model):
    """
        UserChatContext model.
    """

    user = models.ForeignKey(User, on_delete=models.DO_NOTHING, blank=True, null=True)
    platform = models.CharField(max_length=255)

    username = models.CharField(max_length=255)
    chat_id = models.CharField(max_length=255)
    metadata = JSONField(blank=True, null=True)

    updated_at = models.DateTimeField()

    def __str__(self):
        return f"{self.user.email}: {self.username}, {self.chat_id}"
