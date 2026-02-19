from django.urls import path
from .views import logs_view, log_create, activity_add, log_delete

urlpatterns = [
    # can view the activity logs user inputs
    path("logs/", logs_view, name="logs"),
    
    # the url to add new logs and activities
    path("logs/new/", log_create, name="log_create"),
    path("logs/<int:log_id>/activity/new/", activity_add, name="activity_add"),
    path("logs/<int:log_id>/delete/", log_delete, name="log_delete"),
]