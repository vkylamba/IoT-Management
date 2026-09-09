import importlib

from django.conf import settings
from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.urls import path, re_path, reverse
from django.utils import timezone
from django.utils.html import format_html
from django import forms

from iot_server.admin_utils import DjongoSafeModelAdmin

from event.models import Action, DeviceEvent, EventHistory, EventType

if getattr(settings, 'CLICKHOUSE_ENABLED', False):
    from device.clickhouse_models import MeterData
else:
    MeterData = None

admin.site.register(EventType, DjongoSafeModelAdmin)
# admin.site.register(DeviceEvent)
admin.site.register(EventHistory, DjongoSafeModelAdmin)
admin.site.register(Action, DjongoSafeModelAdmin)


class FireForm(forms.Form):

    comment = forms.CharField(
        required=False,
        widget=forms.Textarea,
    )
    send_email = forms.BooleanField(
        required=False,
    )

    def save(self, device_event, user):
        pass


class DeviceEventAdmin(DjongoSafeModelAdmin):

    list_display = (
        'id',
        'typ',
        'device',
        'user',
        'equation_threshold',
        'schedule',
        'Fire_Event'
    )

    def Fire_Event(self, obj):
        return format_html(
            '<a class="button" href="{}">Fire</a>&nbsp;',
            reverse('admin:fire-event', args=[obj.pk]),
        )

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            re_path(
                r'^(?P<event_id>.+)/fireevent/$',
                self.admin_site.admin_view(self.fire_event),
                name='fire-event',
            )
        ]
        return custom_urls + urls

    def fire_event(self, request, event_id, *args, **kwargs):
        device_event = self.get_object(request, event_id)
        if device_event is None:
            self.message_user(request, 'Device event not found.', level=messages.ERROR)
            url = reverse('admin:event_deviceevent_changelist', current_app=self.admin_site.name)
            return HttpResponseRedirect(url)

        data = None
        if device_event.device is not None:
            data = device_event.device.get_last_data_point()

        if not device_event.eval_equation(data):
            self.message_user(request, 'Event condition did not match. No actions were fired.', level=messages.WARNING)
        else:
            executed_actions = 0
            event_actions = Action.objects.filter(device_event=device_event)
            for action in event_actions:
                if not getattr(action, 'active', False):
                    continue
                if not action.task:
                    continue
                if self._run_action_task(action):
                    executed_actions += 1

            device_event.last_trigger_time = timezone.now()
            device_event.save(update_fields=['last_trigger_time'])

            EventHistory.objects.create(
                device_event=device_event,
                result={
                    'manual_fire': True,
                    'executed_actions': executed_actions,
                },
            )
            self.message_user(request, f'Fired event successfully. Executed {executed_actions} action task(s).')
        # if request.method != 'POST':
        #     form = FireForm()
        # else:
        #     form = FireForm(request.POST)
        #     if form.is_valid():
        #         try:
        #             form.save(device_event, request.user)
        #         except Exception as e:
        #             # If save() raised, the form will a have a non
        #             # field error containing an informative message.
        #             pass
        #         else:
        #             # self.message_user(request, 'Success')
        #             url = reverse(
        #                 'admin:event_deviceevent_change',
        #                 args=[device_event.pk],
        #                 current_app=self.admin_site.name,
        #             )
        #             return HttpResponseRedirect(url)

        # context = self.admin_site.each_context(request)
        # context['opts'] = self.model._meta
        # context['form'] = form
        # context['device_event'] = device_event
        # context['title'] = 'Fire Event'
        # return TemplateResponse(
        #     request,
        #     'event/fire_event.html',
        #     context,
        # )

        url = reverse(
            'admin:event_deviceevent_change',
            args=[device_event.pk],
            current_app=self.admin_site.name,
        )
        return HttpResponseRedirect(url)

    def _run_action_task(self, action):
        temp_list = action.task.split('.')
        import_module = '.'.join(temp_list[:-1])
        func_name = temp_list[-1]
        try:
            task_module = importlib.import_module(import_module)
            task = getattr(task_module, func_name, None)
        except Exception:
            return False

        if task is None:
            return False

        if action.args:
            if action.kwargs:
                task(action.id, *action.args, **action.kwargs)
            else:
                task(action.id, *action.args)
        elif action.kwargs:
            task(action.id, **action.kwargs)
        else:
            task(action.id)
        return True


admin.site.register(DeviceEvent, DeviceEventAdmin)
