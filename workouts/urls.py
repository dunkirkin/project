from django.urls import path
from .views import logs_view

# setting url for Daily Log
urlpatterns = [
    path("logs/", logs_view, name="logs"),
]
