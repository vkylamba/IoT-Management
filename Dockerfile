FROM python:3.11
ENV PYTHONUNBUFFERED 1

# create directory for the application user
ENV APP_HOME=/home/application/
RUN mkdir -p $APP_HOME

RUN apt-get update && apt-get install -y supervisor
RUN mkdir -p /var/log/supervisor

# create application user/group first, to be consistent throughout docker variants
RUN set -x \
    && addgroup --system --gid 1001 application \
    && adduser --system --disabled-login --ingroup application --home $APP_HOME --gecos "application user" --shell /bin/false --uid 1001 application

RUN chown -R 1001:0 $APP_HOME

WORKDIR $APP_HOME
COPY ./src/requirements.txt $APP_HOME/requirements.txt

EXPOSE 8000

RUN pip install -r requirements.txt
COPY ./src $APP_HOME

COPY ./supervisord.conf /etc/supervisor/conf.d/supervisord.conf
CMD ["/usr/bin/supervisord"]
