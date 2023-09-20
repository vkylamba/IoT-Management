from django.contrib import admin

from .models import Widget, UserWidget, View

admin.site.register(Widget)
admin.site.register(UserWidget)
admin.site.register(View)
