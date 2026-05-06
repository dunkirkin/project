from django.urls import path
from .views import (
    logs_view, log_create, log_edit, log_delete,
    activity_add, activity_edit, activity_delete,
    history_view, tomorrow_view,
)

urlpatterns = [
    path("logs/", logs_view, name="logs"),
    path("logs/new/", log_create, name="log_create"),
    path("logs/<int:log_id>/edit/", log_edit, name="log_edit"),
    path("logs/<int:log_id>/delete/", log_delete, name="log_delete"),
    path("logs/<int:log_id>/activity/new/", activity_add, name="activity_add"),
    path("activity/<int:activity_id>/edit/", activity_edit, name="activity_edit"),
    path("activity/<int:activity_id>/delete/", activity_delete, name="activity_delete"),
    path("history/", history_view, name="history"),
    path("tomorrow/", tomorrow_view, name="tomorrow"),
]