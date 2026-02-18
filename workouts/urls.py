from django.urls import path
from .views import logs_view, log_create, activity_add

urlpatterns = [
    # can view the activity logs user inputs
    path("logs/", logs_view, name="logs"),
    
    # to add logs & activities
    path("logs/new/", log_create, name="log_create"),
    path("logs/<int:log_id>/activity/new/", activity_add, name="activity_add"),
]