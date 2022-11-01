from django.contrib.auth import get_user_model
from django.contrib.postgres.fields import JSONField
from django.db import models

User = get_user_model()

WIDGET_TYPES = (
    ('Test', 'Test'),
)


class DASHBOARD_SOURCES:
   superset = "superset"


class Widget(models.Model):
    """
        Widget class.
    """
    TYPES = WIDGET_TYPES
    name = models.CharField(max_length=255)
    type = models.CharField(max_length=255, choices=WIDGET_TYPES)
    description = models.TextField(blank=True, null=True)

    metadata = JSONField(blank=True, null=True)

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
    widget = models.ForeignKey('Widget', on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)

    active = models.BooleanField(default=False)
    display_order = models.IntegerField(default=0)
    metadata = JSONField(blank=True, null=True)

    updated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = 'User Widgets'

    def __str__(self):
        return "{}-{}".format(
            self.user,
            self.widget
        )
