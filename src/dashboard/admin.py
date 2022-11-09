from django.contrib import admin

from .models import Widget, UserWidget

admin.site.register(Widget)
admin.site.register(UserWidget)
