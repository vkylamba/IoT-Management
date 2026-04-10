from django import forms
from django.contrib import admin
from iot_server.admin_utils import DjongoSafeModelAdmin

from notification.models import (Notification, SentNotification,
                                 TemplateContext, UserChatContext)


class NotificationAdmin(DjongoSafeModelAdmin):
    list_display = ('name', 'sent', 'title', 'user')
    list_filter = ('name', 'sent', 'title', 'user')

admin.site.register(Notification, NotificationAdmin)
admin.site.register(SentNotification, DjongoSafeModelAdmin)
admin.site.register(UserChatContext, DjongoSafeModelAdmin)

class TemplateContextForm(forms.ModelForm):

    code_result = forms.CharField(required=False)

    class Meta:
        model = TemplateContext
        fields = ('name', 'script', 'code_result')


class TemplateContextAdmin(DjongoSafeModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)
    form = TemplateContextForm


admin.site.register(TemplateContext, TemplateContextAdmin)
