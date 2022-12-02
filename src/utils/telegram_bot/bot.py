import json
import logging
import re
import time
from crypt import methods
from platform import platform
from typing import Tuple

from channels.db import database_sync_to_async
from device.clickhouse_models import data
from device.models import Device, DeviceStatus, User
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from notification.models import Notification, UserChatContext
from telegram import ParseMode, Update
from telegram.ext import (CallbackContext, CommandHandler, Filters,
                          MessageHandler, Updater)
from utils.ip_address import is_valid_ip_address

from .renderers import parse_notification_html, render_status_to_html

logger = logging.getLogger('application')

BOT_TOKEN = settings.TELEGRAM_BOT_TOKEN

updater = Updater(token=BOT_TOKEN)
dispatcher = updater.dispatcher


def create_user_context(update: Update, user: User) -> UserChatContext:
    username = update.message.chat.username
    user_context = UserChatContext.objects.filter(
        user=user,
        platform='telegram',
        username=username
    ).order_by("-id").first()

    if user_context is None:
        user_context = UserChatContext(
            user=user,
            platform='telegram',
            username=username,
            chat_id=update.message.chat_id,
            updated_at=timezone.now()
        )
        user_context.save()

    return user_context

def process_message_from_user(username, message, update):
    valid_email, email = is_valid_email(message)
    valid_ip, ip_numeric = is_valid_ip_address(message)

    user = None
    resp = "Sorry didn't understand it."
    parse_mode = None

    if valid_email:
        logger.info(f"[{username}]: Valid email received form user")
        user = User.objects.filter(email=email).first()


        if user:
            create_user_context(update, user)
            devices = user.device_list()
            resp = f"Found following devices linked to your account: \n{', '.join(devices)}"
            resp += "\nPlease send the device ip address to see the details about."
        else:
            resp = f"No devices found for the email!"

    elif valid_ip:
        logger.info(f"[{username}]: Valid ip address received form user")

        cache_name = f"device_status_{message.strip().lower()}"
        status_data = cache.get(cache_name)
        if status_data is not None:
            status_data = json.loads(status_data)
            resp = render_status_to_html(status_data)
            parse_mode = ParseMode.HTML
        else:
            logger.error(f"Data not found in cache. {cache_name}")
            resp = 'Device/data not found!'

    return resp, parse_mode

def process_user_notifications():
    notifications_list = []
    telegram_users = UserChatContext.objects.all().values('user', 'chat_id')
    users_data = {
        str(x.get('user')): x.get('chat_id') for x in telegram_users
    }
    notifications = Notification.objects.filter(
        method=Notification.TELEGRAM_BOT,
        sent__in=[True],
        user__id__in=users_data.keys()
    )
    updated_notifications = []
    for notification in notifications:
        notification_text = parse_notification_html(notification)
        if notification_text:
            notifications_list.append({
                "chat_id": users_data.get(notification.user.id),
                "text": notification_text,
                "parse_mode": ParseMode.HTML
            })
            notification.sent = True
            updated_notifications.append(notification)
    Notification.objects.bulk_update(updated_notifications, ["sent"])

    return notifications_list

def get_user_info(update: Update):
    username = update.message.chat.username
    first_name = update.message.chat.first_name

    return username, first_name


def is_valid_email(email: str) -> Tuple[bool, str]:
    regex = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    return re.fullmatch(regex, email), email.lower()


def start(update: Update, context: CallbackContext):
    username, first_name = get_user_info(update)
    logger.info(f"[{username}]: start command received form user {first_name}")
    context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"Welcome {first_name}! Please tell me your email id to start with!"
    )


def caps(update: Update, context: CallbackContext):
    text_caps = ' '.join(context.args).upper()
    context.bot.send_message(chat_id=update.effective_chat.id, text=text_caps)


def unknown(update: Update, context: CallbackContext):
    context.bot.send_message(chat_id=update.effective_chat.id,
                             text="Sorry, I didn't understand that command.")


def echo(update: Update, context: CallbackContext):
    username, _ = get_user_info(update)
    message = update.message.text

    logger.info(f"[{username}]: Message received: {message}, chat_id: {update.message.chat_id}")

    try:
        resp, parse_mode = process_message_from_user(username, message, update)
    except Exception as ex:
        logger.exception(ex)
        resp = "Something went wrong!"

    context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=resp,
        parse_mode=parse_mode
    )


def start_bot():
    logger.info("Starting the telegram bot!")
    start_handler = CommandHandler('start', start)
    dispatcher.add_handler(start_handler)

    caps_handler = CommandHandler('caps', caps)
    dispatcher.add_handler(caps_handler)

    unknown_handler = MessageHandler(Filters.command, unknown)
    dispatcher.add_handler(unknown_handler)

    echo_handler = MessageHandler(Filters.text & (~Filters.command), echo)
    dispatcher.add_handler(echo_handler)
    updater.start_polling()

    # Get unsent notifications
    while True:
        try:
            notifications = process_user_notifications()
            for notification in notifications:
                updater.bot.send_message(
                    chat_id=notification.get("chat_id"),
                    text=notification.get("text"),
                    parse_mode=notification.get("parse_mode")
                )
        except Exception as ex:
            logger.exception(ex)
        time.sleep(300)


def stop_bot():
    logger.info("Stopping the telegram bot!")
    updater.stop()
