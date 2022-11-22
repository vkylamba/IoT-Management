python manage.py migrate
python manage.py createsuperuser --email=${DJANGO_SUPERUSER_EMAIL} --noinput
python manage.py runserver 0:8000
tail -f /dev/null
