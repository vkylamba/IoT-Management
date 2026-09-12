#!/bin/bash
echo -e "$ROOT_CA_CERT" > /home/application/root_ca.crt

run_migrations() {
	local migrate_output
	if migrate_output=$(python manage.py migrate 2>&1); then
		echo "$migrate_output"
		return 0
	fi

	echo "$migrate_output"

	if echo "$migrate_output" | grep -q "Migration admin.0001_initial is applied before its dependency device.0001_initial"; then
		echo "Detected inconsistent migration history. Repairing by faking device.0001_initial and retrying migrate."
		python manage.py migrate device 0001_initial --fake
		python manage.py migrate
		return $?
	fi

	return 1
}

run_migrations
python manage.py createsuperuser --email=${DJANGO_SUPERUSER_EMAIL} --noinput
python manage.py collectstatic --no-input
python -m daphne -b 0.0.0.0 -p 8000 iot_server.asgi:application
