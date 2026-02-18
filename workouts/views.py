from django.shortcuts import render

from .models import DailyLog

# Create your views here.

# Lets the daily log be seen on the website as non-admin
def logs_view(request):
    logs = DailyLog.objects.all().prefetch_related("activities")
    return render(request, "workouts/logs.html", {"logs": logs})