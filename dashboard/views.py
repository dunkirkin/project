from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from workouts.models import Activity
from django.db.models import Sum, Count
from django.utils import timezone
from datetime import timedelta

# Create your views here.
@login_required
def dashboard_view(request):
    #Dates
    today = timezone.now().date()
    seven_days_ago = today - timedelta(days=7)

    #Overall Activty Metric

    #going though daily log then matching user with this filter
    acts = Activity.objects.filter(
        daily_log__user = request.user,
        daily_log__date__gte = seven_days_ago
    )
    total_act_mins = acts.aggregate(total=Sum("duration_min"))["total"] or 0
    total_hours = total_act_mins // 60
    mins = total_act_mins % 60
    acts_counts = acts.count()
    daily_total_mins = acts.values("daily_log__date").annotate(total=Sum("duration_min")) or 0

    #Turning daily_total_min into dict
    totals_dict = {
        entry["daily_log__date"] : entry["total"]
        for entry in daily_total_mins
    }

    chart_data = []
    max_mins = 0

    for i in range(7):
        day = seven_days_ago + timedelta(days=i)
        minutes = totals_dict.get(day, 0)
        chart_data.append({
            "day_label": day.strftime("%a"),  # Mon, Tue, etc
            "minutes": minutes
        })
        if minutes > max_mins:
            max_mins = minutes

    # Prevent divide-by-zero
    if max_mins == 0:
        max_mins = 1

    # Add percentage height for scaling bars
    for item in chart_data:
        item["height_percent"] = int((item["minutes"] / max_mins) * 100)

    context = {
        "today" : today,
        "seven_days_ago" : seven_days_ago,
        "total_hours" : total_hours,
        "mins" : mins,
        "act_count" : acts_counts,
        "daily_total_mins" : daily_total_mins,
        "chart_data": chart_data
    }
    return render(request, "dashboard/dashboard.html", context)