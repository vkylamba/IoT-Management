import os
import json
from datetime import datetime, timezone as dt_timezone

from django.conf import settings
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.response import Response


class HealthViewSet(viewsets.ViewSet):
    """Health monitoring endpoints for core background services."""

    permission_classes = ()
    authentication_classes = ()

    def get_health(self, request, format=None):
        checks = self._collect_checks()
        overall = self._calculate_overall_status(checks)
        return Response(
            {
                "status": overall,
                "checked_at": timezone.now().isoformat(),
                "checks": checks,
            },
            status=self._http_status(overall),
        )

    def get_component_health(self, request, component, format=None):
        checks = self._collect_checks()
        if component not in checks:
            return Response(
                {
                    "status": "unknown",
                    "error": f"Unknown component '{component}'.",
                    "available_components": sorted(checks.keys()),
                },
                status=404,
            )

        component_status = checks[component].get("status", "unknown")
        return Response(
            {
                "component": component,
                "checked_at": timezone.now().isoformat(),
                "check": checks[component],
            },
            status=self._http_status(component_status),
        )

    def _collect_checks(self):
        return {
            "mqtt-listener": self._check_mqtt_listener(),
            "celery-workers": self._check_celery_workers(),
            "clickhouse-sync": self._check_clickhouse_sync(),
        }

    def _check_mqtt_listener(self):
        mqtt_enabled = bool(settings.MQTT_BROKER and settings.MQTT_PORT)
        if not mqtt_enabled:
            return {
                "status": "disabled",
                "reason": "MQTT_BROKER or MQTT_PORT is not configured.",
            }

        if not os.path.exists(settings.MQTT_HEALTH_FILE):
            return {
                "status": "unhealthy",
                "reason": "MQTT health heartbeat file not found.",
                "heartbeat_file": settings.MQTT_HEALTH_FILE,
            }

        try:
            with open(settings.MQTT_HEALTH_FILE, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except Exception as ex:
            return {
                "status": "unhealthy",
                "reason": f"Failed to read MQTT heartbeat file: {ex}",
                "heartbeat_file": settings.MQTT_HEALTH_FILE,
            }

        timestamp_raw = payload.get("updated_at")
        if not timestamp_raw:
            return {
                "status": "unhealthy",
                "reason": "MQTT heartbeat does not include updated_at.",
                "heartbeat_file": settings.MQTT_HEALTH_FILE,
                "last_payload": payload,
            }

        try:
            heartbeat_time = datetime.fromisoformat(timestamp_raw)
        except ValueError:
            return {
                "status": "unhealthy",
                "reason": "MQTT heartbeat timestamp is invalid.",
                "heartbeat_file": settings.MQTT_HEALTH_FILE,
                "updated_at": timestamp_raw,
            }

        if heartbeat_time.tzinfo is None:
            heartbeat_time = heartbeat_time.replace(tzinfo=dt_timezone.utc)

        lag_seconds = max((timezone.now() - heartbeat_time).total_seconds(), 0)

        check_status = "healthy" if lag_seconds <= settings.MQTT_HEALTH_STALE_SECONDS else "unhealthy"
        response = {
            "status": check_status,
            "updated_at": heartbeat_time.isoformat(),
            "lag_seconds": int(lag_seconds),
            "stale_after_seconds": settings.MQTT_HEALTH_STALE_SECONDS,
            "state": payload.get("state", "unknown"),
            "heartbeat_file": settings.MQTT_HEALTH_FILE,
        }

        if check_status == "unhealthy":
            response["reason"] = "MQTT heartbeat is stale."

        return response

    def _check_celery_workers(self):
        broker_url = os.getenv("CELERY_BROKER_URL")
        if not broker_url:
            return {
                "status": "disabled",
                "reason": "CELERY_BROKER_URL is not configured.",
            }

        try:
            from celery import Celery
        except Exception as ex:
            return {
                "status": "unhealthy",
                "reason": f"Celery package is unavailable: {ex}",
            }

        try:
            app = Celery("iot-health", broker=broker_url)
            inspector = app.control.inspect(timeout=1.0)
            stats = inspector.stats() if inspector is not None else None

            if not stats:
                return {
                    "status": "unhealthy",
                    "reason": "No Celery workers responded to inspect().",
                }

            workers = sorted(stats.keys())
            return {
                "status": "healthy",
                "worker_count": len(workers),
                "workers": workers,
            }
        except Exception as ex:
            return {
                "status": "unhealthy",
                "reason": f"Failed to query Celery workers: {ex}",
            }

    def _check_clickhouse_sync(self):
        clickhouse_enabled = bool(getattr(settings, "CLICKHOUSE_ENABLED", False))
        if not clickhouse_enabled:
            return {
                "status": "disabled",
                "reason": "ClickHouse is not enabled.",
            }

        try:
            from device.clickhouse_models import MeterData
            latest = MeterData.objects.order_by("-data_arrival_time").first()
        except Exception as ex:
            return {
                "status": "unhealthy",
                "reason": f"ClickHouse query failed: {ex}",
            }

        if latest is None:
            return {
                "status": "degraded",
                "reason": "ClickHouse is reachable but no MeterData is available yet.",
            }

        data_time = latest.data_arrival_time
        if data_time.tzinfo is None:
            data_time = data_time.replace(tzinfo=dt_timezone.utc)

        lag_seconds = max((timezone.now() - data_time).total_seconds(), 0)
        status_text = "healthy" if lag_seconds <= settings.CLICKHOUSE_SYNC_STALE_SECONDS else "unhealthy"

        payload = {
            "status": status_text,
            "latest_data_arrival_time": data_time.isoformat(),
            "lag_seconds": int(lag_seconds),
            "stale_after_seconds": settings.CLICKHOUSE_SYNC_STALE_SECONDS,
        }

        if status_text == "unhealthy":
            payload["reason"] = "ClickHouse sync appears stale."

        return payload

    def _calculate_overall_status(self, checks):
        statuses = [check.get("status", "unknown") for check in checks.values()]
        if "unhealthy" in statuses:
            return "unhealthy"
        if "degraded" in statuses:
            return "degraded"
        if all(status in ("healthy", "disabled") for status in statuses):
            return "healthy"
        return "unknown"

    def _http_status(self, health_status):
        if health_status == "unhealthy":
            return 503
        if health_status == "unknown":
            return 500
        return 200
