FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1
ENV APP_HOME=/home/application

# Run as root to set up folders and permissions first.
USER root
RUN mkdir -p "$APP_HOME" \
    && mkdir -p "$APP_HOME/media" \
    && mkdir -p "$APP_HOME/media/device-reports" \
    && mkdir -p /var/log/supervisor

RUN apt-get update && apt-get install -y --no-install-recommends \
    supervisor \
    gcc \
    libc6-dev \
    libkrb5-dev \
    krb5-multidev \
    procps \
    && rm -rf /var/lib/apt/lists/*

# Create the application user/group first, to be consistent throughout docker variants.
RUN set -x \
    && addgroup --system --gid 1001 application \
    && adduser --system --disabled-login --ingroup application --home "$APP_HOME" --gecos "application user" --shell /bin/false --uid 1001 application

# Ensure the app user owns the media tree used for cached report generation.
RUN chown -R application:application "$APP_HOME" /var/log/supervisor

WORKDIR "$APP_HOME"
COPY ./src/requirements.txt "$APP_HOME/requirements.txt"

EXPOSE 8000

RUN pip install --no-cache-dir -r requirements.txt
COPY ./src "$APP_HOME"
COPY ./supervisord.conf /etc/supervisor/conf.d/supervisord.conf

USER application
CMD ["/usr/bin/supervisord"]
