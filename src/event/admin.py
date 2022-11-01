from device.clickhouse_models import MeterData
from django import forms
from django.conf.urls import url
from django.contrib import admin
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.html import format_html

from event.models import Action, DeviceEvent, EventHistory, EventType

admin.site.register(EventType)
# admin.site.register(DeviceEvent)
admin.site.register(EventHistory)
admin.site.register(Action)


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


class DeviceEventAdmin(admin.ModelAdmin):

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
            url(
                r'^(?P<event_id>.+)/fireevent/$',
                self.admin_site.admin_view(self.fire_event),
                name='fire-event',
            )
        ]
        return custom_urls + urls

    def fire_event(self, request, event_id, *args, **kwargs):
        device_event = self.get_object(request, event_id)
        device = device_event.device
        event_type = device_event.typ.trigger_type
        device_data = None
        if event_type == 'Data':
            last_data = device.get_last_data_point()

            # Create a data object
            voltage = int(input('Enter voltage value(dV): '))
            current = int(input('Enter current value(cA): '))
            time = int(input('Enter time value(in secs): '))
            state = int(input('Enter state value: '))
            latitude = input('Enter latitude value: ')
            longitude = input('Enter longitude value: ')
            power = voltage * current
            device_data = MeterData(
                device=device,
                voltage=voltage,
                current=current,
                power=power,
                energy=last_data.energy + (power * time / 1000),
                runtime=last_data.runtime + time,
                state=state,
                latitude=latitude,
                longitude=longitude
            )
            device_data.save()
        elif event_type == 'Time':
            device_event.trigger_events()
        if device_data:
            device_data.delete()
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


admin.site.register(DeviceEvent, DeviceEventAdmin)
