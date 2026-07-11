from django.contrib import admin
from django.shortcuts import redirect
from django.urls import path

urlpatterns = [
    path('', lambda request: redirect('admin:index', permanent=False)),
    path('admin/', admin.site.urls),
]
