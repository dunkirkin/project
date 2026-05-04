from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from workouts.models import Activity, DailyLog
from django.db.models import Sum, Count, F, ExpressionWrapper, FloatField
from django.utils import timezone
from datetime import timedelta
import math


# ─────────────────────────────────────────────
#  Helper: round up to a "nice" axis max
# ─────────────────────────────────────────────
def _nice_max(val):
    if val <= 0:
        return 1
    nice_options = [1, 2, 3, 5, 8, 10, 12, 15, 20, 25, 30, 50, 75, 100]
    for opt in nice_options:
        if val <= opt:
            return opt
    return math.ceil(val / 50) * 50


# ─────────────────────────────────────────────
#  Helper: build Y-axis tick marks for a chart
# ─────────────────────────────────────────────
def _y_ticks(max_val, num_ticks=4, chart_height=120, pad_top=10, pad_bottom=28):
    plot_height = chart_height - pad_top - pad_bottom
    ticks = []
    for i in range(num_ticks + 1):
        value = max_val * i / num_ticks
        y = pad_top + ((max_val - value) / max_val) * plot_height
        if max_val <= 12:
            display = round(value, 1)
            if display == int(display):
                display = int(display)
        else:
            display = round(value)
        ticks.append({"y": round(y, 1), "label": display})
    return ticks


# ─────────────────────────────────────────────
#  Helper: compute SVG polyline points
# ─────────────────────────────────────────────
def _svg_points(data_list, value_key, chart_width=420, chart_height=140,
                pad_left=24, pad_right=12, pad_top=10, pad_bottom=30, max_val=None):
    """
    Given a list of dicts each with a numeric value at `value_key`,
    compute SVG x/y coordinates and add them to each dict in place.
    Returns the 'points' string for <polyline>.
    Pass max_val to lock the y-axis scale (so chart points line up with axis ticks).
    """
    plot_width = chart_width - pad_left - pad_right
    plot_height = chart_height - pad_top - pad_bottom
    count = len(data_list)
    if max_val is None:
        max_val = max((item[value_key] for item in data_list), default=1) or 1

    for idx, item in enumerate(data_list):
        x = pad_left + (plot_width * idx / max(count - 1, 1))
        y = pad_top + ((max_val - item[value_key]) / max_val) * plot_height
        item["x"] = round(x, 1)
        item["y"] = round(y, 1)
        item["label_y"] = chart_height - 8

    return " ".join(f'{item["x"]},{item["y"]}' for item in data_list)


# ─────────────────────────────────────────────
#  Main Dashboard (7-day overview)
# ─────────────────────────────────────────────
@login_required
def dashboard_view(request):
    today = timezone.localdate()
    seven_days_ago = today - timedelta(days=6)

    # ── Activity block ──
    acts = Activity.objects.filter(
        daily_log__user=request.user,
        daily_log__date__range=(seven_days_ago, today)
    )
    total_act_mins = acts.aggregate(total=Sum("duration_min"))["total"] or 0
    total_hours = total_act_mins // 60
    mins = total_act_mins % 60
    acts_counts = acts.count()
    daily_total_mins = acts.values("daily_log__date").annotate(total=Sum("duration_min"))

    totals_dict = {entry["daily_log__date"]: entry["total"] for entry in daily_total_mins}
    chart_data = []
    max_mins = 0
    for i in range(7):
        day = seven_days_ago + timedelta(days=i)
        minutes = totals_dict.get(day, 0)
        chart_data.append({"day_label": day.strftime("%a"), "minutes": minutes})
        if minutes > max_mins:
            max_mins = minutes
    if max_mins == 0:
        max_mins = 1
    for item in chart_data:
        item["height_percent"] = int((item["minutes"] / max_mins) * 100)

    # ── Training Load ──
    load_expr = ExpressionWrapper(F("duration_min") * F("rpe"), output_field=FloatField())
    weekly_training_load = acts.aggregate(total=Sum(load_expr))["total"] or 0
    avg_daily_load = weekly_training_load / 7
    max_daily_load = 1200
    load_percent = min((avg_daily_load / max_daily_load) * 100, 100)

    # ── Wellness / Stress ──
    logs = DailyLog.objects.filter(user=request.user, date__range=(seven_days_ago, today))
    total7day_wellness = logs.aggregate(total=Sum("wellness"))["total"] or 0
    stress_totals = logs.aggregate(total=Sum("stress"))["total"] or 0
    avg_wellness = round(total7day_wellness / 7, 2)
    avg_stress = round(stress_totals / 7, 2)

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
            "wellness_height": int(((log_entry.wellness if log_entry and log_entry.wellness else 0) / max_stress_well) * 100),
        })

    # ── Sleep Score ──
    sleep_weekly_total = logs.aggregate(total=Sum("sleep_hours"))["total"] or 0
    quality_weekly_total = logs.aggregate(total=Sum("sleep_quality"))["total"] or 0
    avg_quality = float(round(quality_weekly_total / 7, 2))
    avg_sleep_duration = float(round(sleep_weekly_total / 7, 2))
    duration_score = min((avg_sleep_duration / 9) * 100, 100)
    quality_score = (avg_quality / 10) * 100
    sleep_score = round((duration_score * 0.6) + (quality_score * 0.4))
    gauge_degrees = int((sleep_score / 100) * 180)

    sleep_by_day = {entry.date: entry for entry in logs}
    sleep_chart_data = []
    for i in range(7):
        day = seven_days_ago + timedelta(days=i)
        log_entry = sleep_by_day.get(day)
        daily_sleep = float(min((log_entry.sleep_hours / 9) * 100, 100)) if log_entry and log_entry.sleep_hours else 0.0
        daily_quality = float((log_entry.sleep_quality / 10) * 100) if log_entry and log_entry.sleep_quality else 0.0
        daily_score = round((daily_sleep * 0.6) + (daily_quality * 0.4))
        sleep_chart_data.append({"day_label": day.strftime("%a"), "daily_score": daily_score})

    chart_width = 280
    chart_height = 140
    pad_left, pad_right, pad_top, pad_bottom = 18, 12, 10, 30
    plot_width = chart_width - pad_left - pad_right
    plot_height = chart_height - pad_top - pad_bottom
    point_count = len(sleep_chart_data)
    for idx, item in enumerate(sleep_chart_data):
        x = pad_left + (plot_width * idx / max(point_count - 1, 1))
        y = pad_top + ((100 - item["daily_score"]) / 100) * plot_height
        item["x"] = round(x, 1)
        item["y"] = round(y, 1)
        item["label_y"] = chart_height - 8
    sleep_line_points = " ".join(f'{item["x"]},{item["y"]}' for item in sleep_chart_data)

    context = {
        "today": today,
        "seven_days_ago": seven_days_ago,
        "total_hours": total_hours,
        "mins": mins,
        "act_count": acts_counts,
        "chart_data": chart_data,
        "training_load": round(avg_daily_load, 1),
        "load_percent": load_percent,
        "avg_wellness": avg_wellness,
        "avg_stress": avg_stress,
        "wellness_chart_data": wellness_chart_data,
        "sleep_score": sleep_score,
        "gauge_degrees": gauge_degrees,
        "sleep_chart_data": sleep_chart_data,
        "sleep_line_points": sleep_line_points,
    }
    return render(request, "dashboard/dashboard.html", context)


# ─────────────────────────────────────────────
#  Activity Summary Detail
# ─────────────────────────────────────────────
@login_required
def activity_summary_view(request):
    today = timezone.localdate()
    seven_days_ago = today - timedelta(days=6)
    thirty_days_ago = today - timedelta(days=29)

    acts_7 = Activity.objects.filter(
        daily_log__user=request.user,
        daily_log__date__range=(seven_days_ago, today)
    )
    acts_30 = Activity.objects.filter(
        daily_log__user=request.user,
        daily_log__date__range=(thirty_days_ago, today)
    )

    # ── 7-day summary ──
    total_mins_7 = acts_7.aggregate(total=Sum("duration_min"))["total"] or 0
    total_hours_7 = total_mins_7 // 60
    leftover_mins_7 = total_mins_7 % 60
    act_count_7 = acts_7.count()

    # ── Daily bar chart (7 days) ──
    daily_dict = {
        e["daily_log__date"]: e["total"]
        for e in acts_7.values("daily_log__date").annotate(total=Sum("duration_min"))
    }
    chart_data = []
    max_mins = 1
    for i in range(7):
        day = seven_days_ago + timedelta(days=i)
        minutes = daily_dict.get(day, 0)
        chart_data.append({"day_label": day.strftime("%a"), "minutes": minutes})
        if minutes > max_mins:
            max_mins = minutes
    for item in chart_data:
        item["height_percent"] = int((item["minutes"] / max_mins) * 100)

    # ── Activity type breakdown (7 days) ──
    type_breakdown = list(
        acts_7
        .values("activity_type")
        .annotate(count=Count("id"), total_mins=Sum("duration_min"))
        .order_by("-total_mins")
    )
    max_type_mins = max((t["total_mins"] for t in type_breakdown), default=1) or 1
    for t in type_breakdown:
        t["bar_pct"] = int((t["total_mins"] / max_type_mins) * 100)
        t["hours"] = t["total_mins"] // 60
        t["mins"] = t["total_mins"] % 60

    # ── Individual activity list (7 days, newest first) ──
    activity_list = acts_7.select_related("daily_log").order_by("-daily_log__date", "-created_at").values(
        "name_of_activity", "activity_type", "duration_min", "rpe",
        "distance", "distance_unit", "daily_log__date"
    )

    # ── 4-week trend (Mon–Sun aligned) ──
    days_since_monday = today.weekday()  # Monday=0, Sunday=6
    this_monday = today - timedelta(days=days_since_monday)
    weekly_totals = []
    for i in range(4):
        week_start = this_monday - timedelta(weeks=i)
        week_end = week_start + timedelta(days=6)
        total = acts_30.filter(
            daily_log__date__range=(week_start, week_end)
        ).aggregate(total=Sum("duration_min"))["total"] or 0
        weekly_totals.append({
            "label": f"{week_start.strftime('%b %d')} – {week_end.strftime('%b %d')}",
            "total_mins": total,
            "hours": total // 60,
            "mins": total % 60,
        })
    weekly_totals.reverse()
    max_weekly = max((w["total_mins"] for w in weekly_totals), default=1) or 1
    for w in weekly_totals:
        w["bar_pct"] = int((w["total_mins"] / max_weekly) * 100)

    context = {
        "today": today,
        "seven_days_ago": seven_days_ago,
        "total_hours_7": total_hours_7,
        "leftover_mins_7": leftover_mins_7,
        "act_count_7": act_count_7,
        "chart_data": chart_data,
        "type_breakdown": type_breakdown,
        "activity_list": activity_list,
        "weekly_totals": weekly_totals,
    }
    return render(request, "dashboard/activity_summary.html", context)


# ─────────────────────────────────────────────
#  Training Load Detail
# ─────────────────────────────────────────────
@login_required
def training_load_view(request):
    today = timezone.localdate()
    seven_days_ago = today - timedelta(days=6)
    thirty_days_ago = today - timedelta(days=29)

    load_expr = ExpressionWrapper(F("duration_min") * F("rpe"), output_field=FloatField())

    acts_7 = Activity.objects.filter(
        daily_log__user=request.user,
        daily_log__date__range=(seven_days_ago, today)
    )
    acts_30 = Activity.objects.filter(
        daily_log__user=request.user,
        daily_log__date__range=(thirty_days_ago, today)
    )

    # ── Current week ──
    weekly_load = acts_7.aggregate(total=Sum(load_expr))["total"] or 0
    avg_daily_load = weekly_load / 7
    max_daily_load = 1200
    load_percent = min((avg_daily_load / max_daily_load) * 100, 100)

    # ── Zone label ──
    if avg_daily_load < 300:
        zone_label = "Low"
        zone_color = "#4CAF50"
    elif avg_daily_load < 600:
        zone_label = "Moderate"
        zone_color = "#FFC107"
    elif avg_daily_load < 900:
        zone_label = "High"
        zone_color = "#FF9800"
    else:
        zone_label = "Overreaching"
        zone_color = "#FF5722"

    # ── 4-week comparison (Mon–Sun aligned) ──
    days_since_monday = today.weekday()
    this_monday = today - timedelta(days=days_since_monday)
    weekly_loads = []
    for i in range(4):
        week_start = this_monday - timedelta(weeks=i)
        week_end = week_start + timedelta(days=6)
        total = acts_30.filter(
            daily_log__date__range=(week_start, week_end)
        ).aggregate(total=Sum(load_expr))["total"] or 0
        weekly_loads.append({
            "label": f"{week_start.strftime('%b %d')} – {week_end.strftime('%b %d')}",
            "total_load": round(total),
            "avg_daily": round(total / 7, 1),
        })
    weekly_loads.reverse()
    max_load = max((w["total_load"] for w in weekly_loads), default=1) or 1
    for w in weekly_loads:
        w["bar_pct"] = int((w["total_load"] / max_load) * 100)

    # ── Per-activity breakdown (7 days) ──
    acts_with_load = (
        acts_7
        .annotate(load=load_expr)
        .values("name_of_activity", "activity_type", "duration_min", "rpe", "daily_log__date", "load")
        .order_by("-daily_log__date", "-load")
    )
    max_act_load = max((a["load"] for a in acts_with_load if a["load"]), default=1) or 1
    acts_list = []
    for a in acts_with_load:
        acts_list.append({
            **a,
            "load": round(a["load"] or 0),
            "bar_pct": int(((a["load"] or 0) / max_act_load) * 100),
        })

    context = {
        "today": today,
        "seven_days_ago": seven_days_ago,
        "training_load": round(avg_daily_load, 1),
        "weekly_load_total": round(weekly_load),
        "load_percent": load_percent,
        "zone_label": zone_label,
        "zone_color": zone_color,
        "weekly_loads": weekly_loads,
        "acts_list": acts_list,
    }
    return render(request, "dashboard/training_load.html", context)


# ─────────────────────────────────────────────
#  Sleep Score Detail
# ─────────────────────────────────────────────
@login_required
def sleep_score_view(request):
    today = timezone.localdate()
    seven_days_ago = today - timedelta(days=6)
    thirty_days_ago = today - timedelta(days=29)

    logs_7 = DailyLog.objects.filter(user=request.user, date__range=(seven_days_ago, today))
    logs_30 = DailyLog.objects.filter(user=request.user, date__range=(thirty_days_ago, today))

    # ── 7-day sleep score (gauge) — only count days that were actually logged ──
    sleep_logs_7 = logs_7.exclude(sleep_hours__isnull=True)
    sleep_count_7 = sleep_logs_7.count()
    sleep_total_7 = float(sleep_logs_7.aggregate(t=Sum("sleep_hours"))["t"] or 0)
    avg_sleep_7 = round(sleep_total_7 / sleep_count_7, 2) if sleep_count_7 else 0.0

    quality_logs_7 = logs_7.exclude(sleep_quality__isnull=True)
    quality_count_7 = quality_logs_7.count()
    quality_total_7 = quality_logs_7.aggregate(t=Sum("sleep_quality"))["t"] or 0
    avg_quality_7 = round(float(quality_total_7) / quality_count_7, 2) if quality_count_7 else 0.0

    duration_score = min((avg_sleep_7 / 9) * 100, 100)
    quality_score = (avg_quality_7 / 10) * 100
    sleep_score = round((duration_score * 0.6) + (quality_score * 0.4))
    gauge_degrees = int((sleep_score / 100) * 180)

    # ── Best / worst nights (30 days) ──
    logs_with_data = logs_30.exclude(sleep_hours__isnull=True)
    best_sleep = logs_with_data.order_by("-sleep_hours").first()
    worst_sleep = logs_with_data.order_by("sleep_hours").first()
    best_quality = logs_30.exclude(sleep_quality__isnull=True).order_by("-sleep_quality").first()
    worst_quality = logs_30.exclude(sleep_quality__isnull=True).order_by("sleep_quality").first()

    # ── 30-day sleep hours line chart ──
    log_by_date = {log.date: log for log in logs_30}
    hours_chart = []
    quality_chart = []
    for i in range(30):
        day = thirty_days_ago + timedelta(days=i)
        log = log_by_date.get(day)
        hours_chart.append({
            "day_label": day.strftime("%b %d") if i % 5 == 0 else "",
            "sleep_hours": float(log.sleep_hours) if log and log.sleep_hours else 0,
        })
        quality_chart.append({
            "day_label": day.strftime("%b %d") if i % 5 == 0 else "",
            "sleep_quality": log.sleep_quality if log and log.sleep_quality else 0,
        })

    raw_hours_max = max((item["sleep_hours"] for item in hours_chart), default=1) or 1
    hours_axis_max = _nice_max(raw_hours_max)
    hours_line = _svg_points(hours_chart, "sleep_hours", chart_width=560, chart_height=120,
                              pad_left=28, pad_right=12, pad_top=10, pad_bottom=28,
                              max_val=hours_axis_max)
    hours_ticks = _y_ticks(hours_axis_max, num_ticks=4, chart_height=120, pad_top=10, pad_bottom=28)

    raw_quality_max = max((float(item["sleep_quality"]) for item in quality_chart), default=1) or 1
    quality_axis_max = _nice_max(raw_quality_max)
    quality_line = _svg_points(quality_chart, "sleep_quality", chart_width=560, chart_height=120,
                                pad_left=28, pad_right=12, pad_top=10, pad_bottom=28,
                                max_val=quality_axis_max)
    quality_ticks = _y_ticks(quality_axis_max, num_ticks=4, chart_height=120, pad_top=10, pad_bottom=28)

    # ── 30-day averages — only days with data ──
    sleep_logs_30 = logs_30.exclude(sleep_hours__isnull=True)
    sleep_count_30 = sleep_logs_30.count()
    avg_sleep_30 = round(float(sleep_logs_30.aggregate(t=Sum("sleep_hours"))["t"] or 0) / sleep_count_30, 1) if sleep_count_30 else 0.0

    quality_logs_30 = logs_30.exclude(sleep_quality__isnull=True)
    quality_count_30 = quality_logs_30.count()
    avg_quality_30 = round(float(quality_logs_30.aggregate(t=Sum("sleep_quality"))["t"] or 0) / quality_count_30, 1) if quality_count_30 else 0.0

    context = {
        "today": today,
        "seven_days_ago": seven_days_ago,
        "thirty_days_ago": thirty_days_ago,
        "sleep_score": sleep_score,
        "gauge_degrees": gauge_degrees,
        "avg_sleep_7": avg_sleep_7,
        "avg_quality_7": avg_quality_7,
        "best_sleep": best_sleep,
        "worst_sleep": worst_sleep,
        "best_quality": best_quality,
        "worst_quality": worst_quality,
        "hours_chart": hours_chart,
        "quality_chart": quality_chart,
        "hours_line": hours_line,
        "quality_line": quality_line,
        "hours_ticks": hours_ticks,
        "quality_ticks": quality_ticks,
        "avg_sleep_30": avg_sleep_30,
        "avg_quality_30": avg_quality_30,
    }
    return render(request, "dashboard/sleep_score.html", context)


# ─────────────────────────────────────────────
#  Wellness vs Stress Detail
# ─────────────────────────────────────────────
@login_required
def wellness_stress_view(request):
    today = timezone.localdate()
    seven_days_ago = today - timedelta(days=6)
    thirty_days_ago = today - timedelta(days=29)

    logs_7 = DailyLog.objects.filter(user=request.user, date__range=(seven_days_ago, today))
    logs_30 = DailyLog.objects.filter(user=request.user, date__range=(thirty_days_ago, today))

    # ── 7-day bar chart ──
    log_by_date_7 = {log.date: log for log in logs_7}
    bar_chart = []
    for i in range(7):
        day = seven_days_ago + timedelta(days=i)
        log = log_by_date_7.get(day)
        w = log.wellness if log and log.wellness else 0
        s = log.stress if log and log.stress else 0
        bar_chart.append({
            "day_label": day.strftime("%a"),
            "wellness": w,
            "stress": s,
            "wellness_height": int((w / 11) * 100),
            "stress_height": int((s / 11) * 100),
        })

    # ── 7-day averages — only days with data ──
    wellness_logs_7 = logs_7.exclude(wellness__isnull=True)
    w_count_7 = wellness_logs_7.count()
    w_sum = wellness_logs_7.aggregate(t=Sum("wellness"))["t"] or 0
    avg_wellness_7 = round(w_sum / w_count_7, 1) if w_count_7 else 0.0

    stress_logs_7 = logs_7.exclude(stress__isnull=True)
    s_count_7 = stress_logs_7.count()
    s_sum = stress_logs_7.aggregate(t=Sum("stress"))["t"] or 0
    avg_stress_7 = round(s_sum / s_count_7, 1) if s_count_7 else 0.0

    # ── 30-day recovery score line chart ──
    log_by_date_30 = {log.date: log for log in logs_30}
    recovery_chart = []
    for i in range(30):
        day = thirty_days_ago + timedelta(days=i)
        log = log_by_date_30.get(day)
        has_log = log is not None
        score = 0
        if log:
            score = (log.sleep_quality or 0) + (log.wellness or 0) - (log.stress or 0)
        recovery_chart.append({
            "day_label": day.strftime("%b %d") if i % 5 == 0 else "",
            "recovery_score": score,
            "has_log": has_log,
        })

    raw_recovery_max = max((item["recovery_score"] for item in recovery_chart), default=1) or 1
    recovery_axis_max = _nice_max(raw_recovery_max)
    recovery_line = _svg_points(recovery_chart, "recovery_score", chart_width=560, chart_height=120,
                                 pad_left=28, pad_right=12, pad_top=10, pad_bottom=28,
                                 max_val=recovery_axis_max)
    recovery_ticks = _y_ticks(recovery_axis_max, num_ticks=4, chart_height=120, pad_top=10, pad_bottom=28)

    # ── 30-day averages — only days with actual logs ──
    wellness_logs_30 = logs_30.exclude(wellness__isnull=True)
    w_count_30 = wellness_logs_30.count()
    w_sum_30 = wellness_logs_30.aggregate(t=Sum("wellness"))["t"] or 0
    avg_wellness_30 = round(w_sum_30 / w_count_30, 1) if w_count_30 else 0.0

    stress_logs_30 = logs_30.exclude(stress__isnull=True)
    s_count_30 = stress_logs_30.count()
    s_sum_30 = stress_logs_30.aggregate(t=Sum("stress"))["t"] or 0
    avg_stress_30 = round(s_sum_30 / s_count_30, 1) if s_count_30 else 0.0

    logged_scores = [r["recovery_score"] for r in recovery_chart if r["has_log"]]
    avg_recovery_30 = round(sum(logged_scores) / len(logged_scores), 1) if logged_scores else 0.0

    context = {
        "today": today,
        "seven_days_ago": seven_days_ago,
        "thirty_days_ago": thirty_days_ago,
        "bar_chart": bar_chart,
        "avg_wellness_7": avg_wellness_7,
        "avg_stress_7": avg_stress_7,
        "recovery_chart": recovery_chart,
        "recovery_line": recovery_line,
        "recovery_ticks": recovery_ticks,
        "avg_wellness_30": avg_wellness_30,
        "avg_stress_30": avg_stress_30,
        "avg_recovery_30": avg_recovery_30,
    }
    return render(request, "dashboard/wellness_stress.html", context)
