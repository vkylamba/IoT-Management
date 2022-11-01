from api.permissions import IsDeviceUser
from device.models import DevCommand, Device
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django_celery_beat.models import CrontabSchedule, PeriodicTask
from event.models import Action, DeviceEvent, EventHistory, EventType
from notification.models import Notification, TemplateContext
from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response


class EventViewSet(viewsets.ViewSet):
    """
    ViewSet to return device info.
    """
    permission_classes = (IsAuthenticated, IsDeviceUser)

    def get_past_events(self, request, device_id=None):

        # Findout the user
        dev_user = request.user
        if device_id is not None:
            devices = [dev_user.device_list(return_objects=True, device_id=device_id)]
        else:
            devices = dev_user.device_list(return_objects=True)

        from_time = request.data.get('from')
        to_time = request.data.get('to')
        if from_time is not None and to_time is not None:
            from_time = timezone.datetime.strptime(from_time, "%d-%m-%Y")
            to_time = timezone.datetime.strptime(to_time, "%d-%m-%Y")
        else:
            to_time = timezone.now()
            from_time = to_time - timezone.timedelta(days=7)

        # Find the events for the devices
        events = EventHistory.objects.filter(
            device_event__device__in=devices,
            trigger_time__gt=from_time,
            trigger_time__lte=to_time
        ).select_related('device_event', 'device_event__typ', 'device_event__device')

        events_data = []
        for event in events:
            events_data.append({
                'device': event.device_event.device.ip_address,
                'event': event.device_event.typ.name,
                'time': event.trigger_time.strftime(settings.TIME_FORMAT_STRING),
                'type': event.device_event.typ.trigger_type
            })
        return Response(events_data)

    def get_event_types(self, request, *args):

        event_types = EventType.objects.all()
        data = []
        for event_type in event_types:
            event_data = {
                'name': event_type.name,
                'id': event_type.id,
            }
            data.append(event_data)
        return Response(data)

    def get_events(self, request, device_id=None):

        # Findout the user
        dev_user = request.user
        if device_id is not None:
            devices = [dev_user.device_list(return_objects=True, device_id=device_id)]
        else:
            devices = dev_user.device_list(return_objects=True)

        # Find the events for the devices
        actions = Action.objects.filter(
            device_event__device__in=devices
        ).select_related(
            'device_event__typ',
            'device_event__device'
        )

        events_data = {}
        for action in actions:
            device_event = action.device_event
            event = action.device_event.typ
            key = "{}-{}-{}".format(device_event.pk, device_event.device.ip_address, event.name)

            action_data = {
                'id': action.id,
                'name': action.name,
                'device_command': action.device_command.command_name if action.device_command else None,
                'command_parameter': action.command_param,
                'notifications': []
            }
            notifications = action.notifications.all().select_related('context')

            for notification in notifications:
                notification_data = {
                    'id': notification.id,
                    'name': notification.name,
                    'method': notification.method,
                    'emails': notification.emails.split(','),
                    'mobiles': notification.emails.split(','),
                    'title': notification.title,
                    'text': notification.text,
                    'context_id': notification.context.id if notification.context else None,
                    'context': notification.context.name if notification.context else None
                }
                action_data['notifications'].append(notification_data)

            if key not in events_data:
                events_data[key] = {
                    'device': device_event.device.ip_address,
                    'event_id': device_event.pk,
                    'event': event.name,
                    'threshold': device_event.equation_threshold,
                    'schedule': ' '.join(str(device_event.schedule.schedule).split()[1:-1]) if device_event.schedule else None,
                    'event_type': device_event.typ.id,
                    'type': event.trigger_type,
                    'actions': [action_data]
                }
            else:
                events_data[key]['actions'].append(action_data)

        event_types = EventType.objects.all()
        data = []
        for event_type in event_types:
            event_data = {
                'name': event_type.name,
                'id': event_type.id,
            }
            data.append(event_data)

        notifications = Notification.objects.all()
        notifications_data = []
        for notification in notifications:
            notification_data = {
                'name': notification.name,
                'id': notification.id
            }
            notifications_data.append(notification_data)

        resp_data = {
            'events': events_data,
            'event_types': data,
            'notifications': notifications_data
        }
        return Response(resp_data)

    def get_event(self, request, dev_event_id):

        # Find the event
        try:
            dev_event = DeviceEvent.objects.get(pk=dev_event_id)
        except DeviceEvent.DoesNotExist:
            response = {
                'success': False,
                'error': 'Event not found.'
            }
            return Response(response, status=status.HTTP_400_BAD_REQUEST)

        event_data = {
            'device': dev_event.device.ip_address,
            'event_type_id': dev_event.typ.id,
            'event_type': dev_event.typ.name,
            'type': dev_event.typ.trigger_type,
            'limit': dev_event.equation_threshold,
            'schedule': str(dev_event.schedule),
            'actions': [],
            # 'available_event_types': [{'name': etpe.name, 'id': etpe.id} for etpe in EventType.objects.all()]
        }

        event_actions = Action.objects.filter(device_event=dev_event).prefetch_related('notifications__context')
        for event_action in event_actions:
            action_data = {
                'id': event_action.id,
                'name': event_action.name,
                'device_command': event_action.device_command,
                'command_parameter': event_action.command_param,
                'notifications': []
            }
            notifications = event_action.notifications.all().select_related('context')

            for notification in notifications:
                notification_data = {
                    'id': notification.id,
                    'name': notification.name,
                    'method': notification.method,
                    'emails': notification.emails.split(','),
                    'mobiles': notification.emails.split(','),
                    'title': notification.title,
                    'text': notification.text,
                    'context_id': notification.context.id if notification.context else None,
                    'context': notification.context.name if notification.context else None
                }
                action_data['notifications'].append(notification_data)

            event_data['actions'].append(action_data)
        return Response(event_data)

    @transaction.atomic
    def create_event(self, request, dev_event_id=None):

        event_data = request.data

        if dev_event_id is None:
            dev_event = DeviceEvent()
        else:
            try:
                dev_event = DeviceEvent.objects.get(pk=dev_event_id)
            except DeviceEvent.DoesNotExist:
                response = {
                    'success': False,
                    'error': "Device event not found."
                }
                return Response(response, status=status.HTTP_400_BAD_REQUEST)

        device_ip_address = event_data.get('ipAddress')
        event_id = event_data.get('eventId')
        error = []
        try:
            device = Device.objects.get(ip_address=device_ip_address)
        except Device.DoesNotExist:
            error.append("Device {} not found".format(device_ip_address))

        try:
            event = EventType.objects.get(pk=event_id)
        except EventType.DoesNotExist:
            error.append("Event {} not found".format(event_id))

        if len(error) == 0:
            dev_event.user = request.user
            dev_event.device = device
            dev_event.typ = event
            if event_data.get('thresholdValue') and event.equation is not None:
                dev_event.equation_threshold = event_data.get('thresholdValue')
            if event_data.get('schedule'):
                # Find the schedule
                event_schedule = event_data.get('schedule').split()
                if len(event_schedule) > 4:
                    schedule, created = CrontabSchedule.objects.get_or_create(
                        minute=event_schedule[0],
                        hour=event_schedule[1],
                        day_of_week=event_schedule[2],
                        day_of_month=event_schedule[3],
                        month_of_year=event_schedule[4],
                    )
                    if created:
                        schedule.save()
                    dev_event.schedule = schedule

            dev_event.save()

            actions = event_data.get('actions', [])
            for action_data in actions:
                if action_data.get('actionId'):
                    action = Action.objects.get(pk=action_data.get('actionId'))
                else:
                    action = Action()

                if not action.name:
                    action.name = "{}-{}-Action".format(event.name, device_ip_address)
                if action_data.get('command'):
                    command = DevCommand.objects.get(device=device, command_name=action_data.get('command'))
                    action.device_command = command
                    action.command_param = action_data.get('commandValue')
                action.device_event = dev_event
                action.save()

                notifications = action_data.get('notifications')
                for notification_data in notifications:
                    if notification_data.get('notificationId'):
                        notification = Notification.objects.get(pk=notification_data.get('notificationId'))
                    else:
                        notification = Notification()
                        notification.name = notification_data.get('name')
                        notification.title = notification_data.get('title')
                        notification.emails = ','.join(notification_data.get('emails', []))
                        notification.mobiles = ','.join(notification_data.get('mobiles', []))
                        notification.text = notification_data.get('text')

                        if notification_data.get('contextId'):
                            notification.context = TemplateContext.objects.get(pk=notification_data.get('contextId'))
                        notification.save()
                    action.notifications.add(notification)
                    action.save()

            data = {
                'success': True
            }
            return Response(data)
        else:
            data = {
                'success': False,
                'error': ','.join(error)
            }
            return Response(data, status=status.HTTP_400_BAD_REQUEST)

    @transaction.atomic
    def delete_event(self, required, dev_event_id):
        # Find the event
        try:
            dev_event = DeviceEvent.objects.get(pk=dev_event_id)
            dev_event.delete()
        except DeviceEvent.DoesNotExist:
            response = {
                'success': False,
                'error': 'Event not found.'
            }
            return Response(response, status=status.HTTP_400_BAD_REQUEST)
        return Response(status=status.HTTP_200_OK)
