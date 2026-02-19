from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from .forms import DailyLogForm, ActivityForm
from .models import DailyLog

from .models import DailyLog

# Create your views here.

# Lets the daily log be seen on the website as non-admin
def logs_view(request):
    logs = DailyLog.objects.all().prefetch_related("activities")
    return render(request, "workouts/logs.html", {"logs": logs})

# allows user to delete logs
# bugs out if try to delete other user's log
@login_required
def log_delete(request, log_id):
    log = get_object_or_404(DailyLog, id=log_id, user=request.user)
    
    if request.method == "POST":
        log.delete()
        return redirect("logs")
    
    return render(request, "workouts/log_confirm_delete.html", {"log": log})

# allows user to post logs, but requires a log in
@login_required
def log_create(request):
    if request.method == "POST":
        form = DailyLogForm(request.POST)
        if form.is_valid():
            log = form.save(commit=False)
            log.user = request.user
            # if already have a log for that date, this will error due to unique_together.
            try:
                log.save()
            except Exception:
                form.add_error("date", "You already have a log for this date.")
            else:
                return redirect("logs")
    else:
        form = DailyLogForm()

    return render(request, "workouts/log_create.html", {"form": form})

# allowing user to add their activities
@login_required
def activity_add(request, log_id):
    log = get_object_or_404(DailyLog, id=log_id, user=request.user)

    if request.method == "POST":
        form = ActivityForm(request.POST)
        if form.is_valid():
            activity = form.save(commit=False)
            activity.daily_log = log
            activity.save()
            return redirect("logs")
    else:
        form = ActivityForm()

    return render(request, "workouts/activity_add.html", {"form": form, "log": log})