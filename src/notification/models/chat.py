import uuid

from device.models import User
from django.db import models


class UserChatContext(models.Model):
    """
        UserChatContext model.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.DO_NOTHING, blank=True, null=True)
    platform = models.CharField(max_length=255)

    username = models.CharField(max_length=255)
    chat_id = models.CharField(max_length=255)
    metadata = models.JSONField(blank=True, null=True)

    updated_at = models.DateTimeField()

    def __str__(self):
        return f"{self.user.email}: {self.username}, {self.chat_id}"
