from django import forms
from django.contrib import admin

from notification.models import (Notification, SentNotification,
                                 TemplateContext, UserChatContext)

admin.site.register(Notification)
admin.site.register(SentNotification)
admin.site.register(UserChatContext)

class TemplateContextForm(forms.ModelForm):

    code_result = forms.CharField(required=False)

    class Meta:
        model = TemplateContext
        fields = ('name', 'script', 'code_result')


class TemplateContextAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)
    form = TemplateContextForm


admin.site.register(TemplateContext, TemplateContextAdmin)
