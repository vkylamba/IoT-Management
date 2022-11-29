python manage.py migrate
python manage.py createsuperuser --email=${DJANGO_SUPERUSER_EMAIL} --noinput
python manage.py collectstatic --no-input
python manage.py startbot &
daphne -b 0.0.0.0 -p 8000 iot_server.asgi:application
tail -f /dev/null
