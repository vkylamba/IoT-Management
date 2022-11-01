python manage.py collectstatic --no-input
python manage.py migrate

if [ "$IS_CELERY_WORKER" -eq "1" ]
then
    celery -A iot_server worker -l info
elif [ "$IS_CELERY_BEAT" -eq "1" ]
then
    celery -A iot_server beat -l info -S django
elif [ "$WEB_WORKERS" -gt "0" ]
then
    # gunicorn iot_server.wsgi:application --bind 0.0.0.0:8000 --workers $WEB_WORKERS --timeout 300
    python manage.py startbot &
    daphne -b 0.0.0.0 -p 8000 iot_server.asgi:application
fi

tail -f /dev/null
