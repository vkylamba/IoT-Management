from django.contrib import admin
from iot_server.admin_utils import DjongoSafeModelAdmin

from .models import Widget, UserWidget, View

admin.site.register(Widget, DjongoSafeModelAdmin)
admin.site.register(UserWidget, DjongoSafeModelAdmin)
admin.site.register(View, DjongoSafeModelAdmin)
