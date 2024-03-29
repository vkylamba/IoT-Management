!/bin/bash
echo -e $ROOT_CA_CERT > /home/application/root_ca.crt
python manage.py migrate
python manage.py createsuperuser --email=${DJANGO_SUPERUSER_EMAIL} --noinput
python manage.py collectstatic --no-input
python -m daphne -b 0.0.0.0 -p 8000 iot_server.asgi:application
