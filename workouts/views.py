from datetime import date, timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.shortcuts import render, redirect, get_object_or_404
from .forms import DailyLogForm, ActivityForm
from .models import DailyLog, Activity


# Per-activity scaling applied to the global zone duration range.
# 1.0 = same as zone baseline; >1 means typically a longer session,
# <1 means typically shorter (e.g. swim is more intense per minute).
ACTIVITY_DURATION_MULT = {
    "Run":          1.00,
    "Bike":         1.30,
    "Moutain Bike": 1.20,  # matches the spelling in Activity.ACTIVITY_CHOICES
    "Hike":         1.30,
    "Walk":         1.10,
    "Swim":         0.50,
    "Lift":         0.80,
    "Yoga":         0.85,
    "Sport":        1.00,
    "Other":        1.00,
}


def _scale_duration(activity_type, low, high):
    """Scale the (low, high) zone range by the activity's multiplier, rounded to nearest 5 min."""
    mult = ACTIVITY_DURATION_MULT.get(activity_type, 1.0)
    new_low = max(5, round(low * mult / 5) * 5)
    new_high = round(high * mult / 5) * 5
    if new_high <= new_low:
        new_high = new_low + 5
    return new_low, new_high

# Create your views here.

# Lets the daily log be seen on the website as non-admin
@login_required
def logs_view(request):
    logs = (
        DailyLog.objects
        .filter(user=request.user)
        .prefetch_related("activities")
        .order_by("-date")
    )
    return render(request, "workouts/logs.html", {"logs": logs})

# allows user to delete logs
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

# history page — all activities ever logged, newest first
@login_required
def history_view(request):
    activities = (
        Activity.objects
        .filter(daily_log__user=request.user)
        .select_related("daily_log")
        .order_by("-daily_log__date", "-created_at")
    )
    newest = activities.first()
    oldest = activities.last()
    context = {
        "activities": activities,
        "total_count": activities.count(),
        "first_date": oldest.daily_log.date if oldest else None,
        "last_date": newest.daily_log.date if newest else None,
    }
    return render(request, "workouts/history.html", context)


@login_required
def tomorrow_view(request):
    today = date.today()
    tomorrow = today + timedelta(days=1)

    # Anchor: use today's log if it exists, else fall back to yesterday
    try:
        anchor_log = DailyLog.objects.prefetch_related("activities").get(
            user=request.user, date=today
        )
        has_today_log = True
    except DailyLog.DoesNotExist:
        has_today_log = False
        yesterday = today - timedelta(days=1)
        try:
            anchor_log = DailyLog.objects.prefetch_related("activities").get(
                user=request.user, date=yesterday
            )
        except DailyLog.DoesNotExist:
            anchor_log = None

    anchor_activities = list(anchor_log.activities.all()) if anchor_log else []

    # Last 7 calendar days of logs
    week_start = today - timedelta(days=6)
    logs_7 = (
        DailyLog.objects
        .filter(user=request.user, date__gte=week_start, date__lte=today)
        .prefetch_related("activities")
    )

    # --- Rest day check ---
    # Trigger 1: sleep < 2 hours on anchor day
    rest_day = bool(
        anchor_log
        and anchor_log.sleep_hours is not None
        and anchor_log.sleep_hours < 2
    )
    # Trigger 2: 120+ minutes at RPE 9 or 10 on anchor day
    high_rpe_minutes = sum(
        a.duration_min for a in anchor_activities
        if a.rpe is not None and a.rpe >= 9
    )
    if high_rpe_minutes >= 120:
        rest_day = True

    # --- Anchor day load ---
    rpe_vals = [a.rpe for a in anchor_activities if a.rpe is not None]
    yesterday_rpe_avg = sum(rpe_vals) / len(rpe_vals) if rpe_vals else 0
    yesterday_duration = sum(a.duration_min for a in anchor_activities)
    yesterday_high_effort = yesterday_rpe_avg >= 8 or yesterday_duration >= 90

    # --- 7-day sleep averages ---
    sleep_hours_list = [float(l.sleep_hours) for l in logs_7 if l.sleep_hours is not None]
    sleep_quality_list = [float(l.sleep_quality) for l in logs_7 if l.sleep_quality is not None]
    avg_sleep_hours = sum(sleep_hours_list) / len(sleep_hours_list) if sleep_hours_list else None
    avg_sleep_quality = sum(sleep_quality_list) / len(sleep_quality_list) if sleep_quality_list else None
    bad_sleep_7 = (
        (avg_sleep_hours is not None and avg_sleep_hours < 6)
        or (avg_sleep_quality is not None and avg_sleep_quality < 5)
    )

    # --- Base duration: average total daily workout minutes over past 7 days ---
    daily_durations = []
    for log in logs_7:
        total = sum(a.duration_min for a in log.activities.all())
        if total > 0:
            daily_durations.append(total)
    base_duration = round(sum(daily_durations) / len(daily_durations)) if daily_durations else 30

    # --- Intensity zone ---
    # Priority order: REST → RECOVERY → EASY → HARD → MODERATE (default)
    good_sleep_7 = (
        avg_sleep_hours is not None and avg_sleep_hours > 7.5
        and avg_sleep_quality is not None and avg_sleep_quality > 7
    )
    if rest_day:
        zone = "REST"
    elif yesterday_high_effort:
        zone = "RECOVERY"
    elif bad_sleep_7:
        zone = "EASY"
    elif good_sleep_7 and yesterday_rpe_avg <= 4:
        zone = "HARD"
    else:
        zone = "MODERATE"

    # --- Duration range (rounded to nearest 5 min) ---
    def to5(n):
        return max(5, round(n / 5) * 5)

    duration_multipliers = {
        "REST":     (None, None),
        "RECOVERY": (0.40, 0.55),
        "EASY":     (0.60, 0.75),
        "MODERATE": (0.90, 1.10),
        "HARD":     (1.10, 1.30),
    }
    low_mult, high_mult = duration_multipliers[zone]
    if low_mult is None:
        dur_low = dur_high = None
    else:
        dur_low = to5(base_duration * low_mult)
        dur_high = to5(base_duration * high_mult)
        if dur_low == dur_high:
            dur_high = dur_low + 5

    zone_labels = {
        "REST":     "Rest Day",
        "RECOVERY": "Recovery",
        "EASY":     "Easy",
        "MODERATE": "Moderate",
        "HARD":     "Hard",
    }
    rpe_ranges = {
        "REST":     None,
        "RECOVERY": "1–3",
        "EASY":     "4–5",
        "MODERATE": "6–7",
        "HARD":     "8–9",
    }

    # --- Suggested workouts (up to 3 cards) ---
    if zone == "REST":
        # Light recovery only — fixed list of low-effort options
        suggestions = [
            {"name": "Walk",    "low": 20, "high": 30},
            {"name": "Stretch", "low": 15, "high": 20},
            {"name": "Yoga",    "low": 25, "high": 30},
        ]
    else:
        thirty_days_ago = today - timedelta(days=29)
        top_types = list(
            Activity.objects
            .filter(daily_log__user=request.user, daily_log__date__gte=thirty_days_ago)
            .values("activity_type")
            .annotate(count=Count("id"))
            .order_by("-count", "activity_type")[:3]
        )
        if not top_types:
            # User has no activity history in the last 30 days — fall back to a single generic card
            suggestions = [
                {"name": f"{zone_labels[zone]} Workout", "low": dur_low, "high": dur_high},
            ]
        else:
            suggestions = []
            for entry in top_types:
                atype = entry["activity_type"]
                low, high = _scale_duration(atype, dur_low, dur_high)
                suggestions.append({"name": atype, "low": low, "high": high})

    context = {
        "tomorrow": tomorrow,
        "zone": zone,
        "zone_label": zone_labels[zone],
        "rpe_range": rpe_ranges[zone],
        "dur_low": dur_low,
        "dur_high": dur_high,
        "suggestions": suggestions,
        "has_today_log": has_today_log,
        "avg_sleep_hours": round(avg_sleep_hours, 1) if avg_sleep_hours is not None else None,
        "avg_sleep_quality": round(avg_sleep_quality, 1) if avg_sleep_quality is not None else None,
        "base_duration": base_duration,
    }
    return render(request, "workouts/tomorrow.html", context)


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