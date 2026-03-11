from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from workouts.models import Activity
from workouts.models import DailyLog
from django.db.models import Sum, Count, F, ExpressionWrapper, FloatField
from django.utils import timezone
from datetime import timedelta

# Create your views here.
@login_required
def dashboard_view(request):
    #Dates
    today = timezone.localdate()
    seven_days_ago = today - timedelta(days=6)

    #Overall Activty Metric

    #going though daily log then matching user with this filter
    acts = Activity.objects.filter(
        daily_log__user = request.user,
        daily_log__date__range = (seven_days_ago, today)
    )
    total_act_mins = acts.aggregate(total=Sum("duration_min"))["total"] or 0
    total_hours = total_act_mins // 60
    mins = total_act_mins % 60
    acts_counts = acts.count()
    daily_total_mins = acts.values("daily_log__date").annotate(total=Sum("duration_min"))

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


    # Training Load Metric
    # Training load is computed as SUM(duration_min * rpe)

    load_expression = ExpressionWrapper(
        F("duration_min") * F("rpe"),
        output_field=FloatField()
    )

    weekly_training_load = acts.aggregate(total=Sum(load_expression))["total"] or 0

    # Convert to an average daily training load (past 7 days)
    avg_daily_load = weekly_training_load / 7

    # Visualization scale
    # Full bar represents 120 minutes at RPE 10
    # 120 * 10 = 1200
    max_daily_load = 1200

    load_percent = min((avg_daily_load / max_daily_load) * 100, 100)


    #Recovery Score
    #Based on Sleep hours, sleep quality
    logs = DailyLog.objects.filter(
    user=request.user,
    date__range=(seven_days_ago, today)
)
    total7day_wellness = logs.aggregate(total=Sum("wellness"))["total"] or 0
    stress_totals = logs.aggregate(total=Sum("stress"))["total"] or 0
    avg_wellness = round(total7day_wellness/7, 2)
    avg_stress = round(stress_totals/7, 2)

    wellness_by_day = {entry.date: entry for entry in logs}
    wellness_chart_data = []
    max_stress_well = 11
    for i in range(7):
        day = seven_days_ago + timedelta(days=i)
        log_entry = wellness_by_day.get(day)
        wellness_chart_data.append({
            "day_label": day.strftime("%a"),
            "wellness": log_entry.wellness if log_entry and log_entry.wellness else 0,
            "stress": log_entry.stress if log_entry and log_entry.stress else 0,
            "stress_height": int(((log_entry.stress if log_entry and log_entry.stress else 0) / max_stress_well) * 100),
            "wellness_height": int(((log_entry.wellness if log_entry and log_entry.wellness else 0) / max_stress_well) * 100)
        })

    # Basic recommendation for tomorrow
    if avg_wellness >= 7 and avg_stress <= 4 and avg_daily_load < 300:
        recommended_activity = "You seem well recovered. A moderate to hard workout is okay tomorrow."
    elif avg_wellness >= 5 and avg_stress <= 6:
        recommended_activity = "A moderate workout or light cardio is recommended tomorrow."
    else:
        recommended_activity = "Take it easy tomorrow. Light activity, walking, stretching, or rest is recommended."

    context = {
        "today" : today,
        "seven_days_ago" : seven_days_ago,
        "total_hours" : total_hours,
        "mins" : mins,
        "act_count" : acts_counts,
        "daily_total_mins" : daily_total_mins,
        "chart_data": chart_data,
        "training_load": round(avg_daily_load, 1),
        "load_percent": load_percent,
        "avg_wellness": avg_wellness,
        "avg_stress": avg_stress,
        "wellness_chart_data": wellness_chart_data,
        "recommended_activity": recommended_activity,
    }
    return render(request, "dashboard/dashboard.html", context)