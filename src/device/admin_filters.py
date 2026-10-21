from django.contrib import admin

from device.models.device import Device


class DeviceIpAddressAdminFilter(admin.SimpleListFilter):
    """
    Filter high-volume collections by device IP using device_id (indexed meta field
    on the device_devicestatus time series), instead of device__ip_address joins.
    """

    title = "device IP"
    parameter_name = "device_ip"

    def lookups(self, request, model_admin):
        rows = (
            Device.objects.exclude(ip_address__isnull=True)
            .exclude(ip_address="")
            .order_by("ip_address")
            .values_list("ip_address", flat=True)[:300]
        )
        return [(ip, ip) for ip in rows]

    def queryset(self, request, queryset):
        ip = self.value()
        if not ip:
            return queryset
        device = Device.objects.filter(ip_address=ip).only("id").first()
        if not device:
            return queryset.none()
        return queryset.filter(device_id=device.pk)
