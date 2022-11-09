import json as json_handler
import logging
import uuid
from datetime import datetime

from device.models import User
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db import models
from django.template import Context, Template
from django.utils import timezone
from utils import DataReports

from notification.http_requests import send_get_requests, send_post_requests

logger = logging.getLogger('application')

# Create your models here.


NotificationMethods = (
    ('S', 'Via SMS'),
    ('E', 'Via email'),
    ('P', 'Push notification'),
    ('HG', 'HTTP GET request'),
    ('HP', 'HTTP POST request'),
    ('TB', 'Telegram bot'),
)


class Notification(models.Model):
    """
        Notification model.
    """
    SMS = 'S'
    EMAIL = 'E'
    PUSH_NOTIFICATION = 'P'
    HTTP_GET = 'HG'
    HTTP_POST = 'HP'
    TELEGRAM_BOT = 'TB'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    user = models.ForeignKey(User, blank=True, null=True, on_delete=models.CASCADE)
    method = models.CharField(max_length=2, choices=NotificationMethods)
    sent = models.BooleanField(default=False)
    mobiles = models.TextField(help_text='Comma separated list of mobile numbers.', blank=True, null=True)
    emails = models.TextField(help_text='Comma separated list of emails.', blank=True, null=True)
    urls = models.TextField(help_text='Comma separated list of URLs.', blank=True, null=True)
    title = models.CharField(max_length=255, null=True, blank=True, help_text='Notification title')
    context = models.ForeignKey('TemplateContext', null=True, blank=True, on_delete=models.CASCADE)
    text = models.TextField(null=True, blank=True, help_text='Notification text')
    data = models.JSONField(help_text='Json dictionary', blank=True, null=True)

    def __str__(self):
        return f"{self.name} - {self.sent}"

    def send(self, event):
        """
            Method to send notifications
        """
        logger.info("Preparing notification for event: {}".format(event))
        template = Template(self.text)
        context_dictionary = {
            "event": event,
            "device": event.device,
            "trigger_time": datetime.now().strftime("%d-%m-%Y %H:%M"),
        }
        if self.context is not None:
            context_dictionary.update(
                self.context.get_context(event)
            )
        context = Context(context_dictionary)
        logger.info("Context is: {}".format(context))
        text = template.render(context)
        json = Template(self.json).render(context)
        # json = "{\"data\": \"1,2,3,4,5,6,7\"}"
        logger.info("Notification text is: {}".format(text))
        logger.info("Notification json is: {}".format(json))
        if self.method == 'E':
            email_recipients = self.emails.split(',')

            subject, from_email, to = self.title, settings.EMAIL_HOST_USER, email_recipients
            text_content = text
            html_content = text
            msg = EmailMultiAlternatives(subject, text_content, from_email, to)
            msg.attach_alternative(html_content, "text/html")
            msg.send()
        elif self.method == 'S':
            pass
        elif self.method == 'P':
            # recipients are emails this time
            pass
        elif self.method == 'HG':
            request_recipients = self.urls.split(',')
            path = ''
            data = {}
            if self.title is not None:
                path = self.title
            if self.json is not None:
                data = json_handler.loads(json)
            send_get_requests(request_recipients, path, data)
        elif self.method == 'HP':
            request_recipients = self.urls.split(',')
            path = ''
            data = {}
            if self.title is not None:
                path += self.title
            if self.json is not None:
                data = json_handler.loads(json)
            send_post_requests(request_recipients, path, data)


class TemplateContext(models.Model):
    """
        Model to store template context.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    script = models.TextField(null=True, blank=True, help_text='Write the context generator script here.')

    def get_context(self, event):
        logger.info('Generating context for event {}'.format(event))
        # try:
        exec(self.script)
        the_context = locals().get('context')
        # except Exception as e:
        #     logger.error(e)
        logger.info("Done context generation.")
        return the_context

    def __str__(self):
        return self.name


class SentNotification(models.Model):
    """
        Sent notifications model.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    notification = models.ForeignKey(Notification, on_delete=models.CASCADE)
    event = models.ForeignKey('event.EventHistory', blank=True, null=True, on_delete=models.CASCADE)
    sent_time = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return "{notif} - {time}".format(notif=self.notification, time=self.sent_time.strftime("%d-%m-%Y %H:%M:%S"))
