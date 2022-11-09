import uuid

from django.contrib.auth import get_user_model
from django.db import models

User = get_user_model()

WIDGET_TYPES = (
    ('Chart', 'Chart'),
    ('Table', 'Table'),
    ('Favorite', 'Favorite'),
    ('Other', 'Other'),
)


class DASHBOARD_SOURCES:
   superset = "superset"


class Widget(models.Model):
    """
        Widget class.
    """
    CHART = "Chart"
    TABLE = "Table"
    FAVORITE = "Favorite"
    OTHER = "Other"

    name = models.CharField(max_length=255, primary_key=True)
    type = models.CharField(max_length=255, choices=WIDGET_TYPES)
    description = models.TextField(blank=True, null=True)

    metadata = models.JSONField(blank=True, null=True)

    class Meta:
        verbose_name_plural = 'Widgets'
        unique_together = ('name', 'type')

    def __str__(self):
        return "{}-{}".format(
            self.type,
            self.name
        )


class UserWidget(models.Model):
    """
        Widget class.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    widget = models.ForeignKey('Widget', on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)

    active = models.BooleanField(default=False)
    display_order = models.IntegerField(default=0)
    metadata = models.JSONField(blank=True, null=True)

    updated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = 'User Widgets'

    def __str__(self):
        return "{}-{}".format(
            self.user,
            self.widget
        )
