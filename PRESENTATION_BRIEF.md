# Athletic Insight — Final Project Brief

> **For PPT generation:** This document is a complete reference for the Athletic Insight web application. Every algorithm, calculation, feature, and architectural detail is captured below. Use it to generate slides covering project overview, technical architecture, algorithms, UI flow, and outcomes.

---

## 1. Project Overview

**Athletic Insight** is a personal athletic tracking web application built with Django. It is designed for individual athletes (runners, cyclists, swimmers, lifters, hikers, etc.) to log daily wellness and workout data, and receive data-driven, personalized recommendations for the next day's training.

### What problem does it solve?
Athletes log workouts in apps like Strava, but those apps don't help decide *what to do tomorrow*. Coaches give advice based on subjective recovery — sleep, soreness, stress — but most apps ignore those signals. Athletic Insight bridges this gap by combining **objective load data** (RPE × duration) with **subjective recovery data** (sleep hours/quality, wellness, stress) to recommend an appropriate intensity, duration, and activity choice for the next training session.

### Core user flow
1. User signs up / logs in
2. Each day they create a **Daily Log** (date, sleep hours, sleep quality, wellness, stress, optional notes)
3. Each daily log can hold **multiple activities** (a swim + a run + a lift = three Activity rows tied to one DailyLog)
4. User views the **Dashboard** with 7-day summary metrics (Activity Summary, Training Load, Sleep Score, Wellness vs Stress)
5. Each metric card is clickable and navigates to a detail page with 30-day charts and breakdowns
6. User views the **Tomorrow's Plan** page to get a personalized workout recommendation
7. User views **History** to see every activity ever logged in a Strava-style table

---

## 2. Technical Architecture

### Stack
- **Backend framework:** Django 6.0 (Python)
- **Database:** SQLite (development)
- **Frontend:** Server-rendered Django templates with vanilla CSS — no React, no JavaScript framework
- **Charts:** Hand-rendered SVG generated server-side (no Chart.js or D3). Polyline points and Y-axis ticks are computed in Python and passed to templates
- **Auth:** Django's built-in `django.contrib.auth` (login_required decorator on every view)
- **Timezone:** `America/Los_Angeles` (set in `config/settings.py`) so dates display correctly for the user

### Django apps (each is a self-contained module)
| App | Purpose |
|---|---|
| `pages` | Landing page / public-facing pages |
| `accounts` | User signup, login redirects |
| `workouts` | DailyLog and Activity models, daily-log CRUD, activity logging, tomorrow-plan view, history view |
| `dashboard` | Dashboard view + 4 detail metric pages |
| `config` | Project settings, root URL conf, WSGI/ASGI |

### Database schema (2 main models)

**DailyLog** — represents one day per user
```
- user            FK to User
- date            DateField (unique per user)
- sleep_hours     Decimal (1 decimal place, nullable)
- sleep_quality   Decimal 0–10 (validators enforced, nullable)
- wellness        Decimal 0–10 (validators enforced, nullable)
- stress          Decimal 0–10 (validators enforced, nullable)
- notes           TextField
- created_at      auto timestamp
- unique_together (user, date)  → one log per day per user
```

**Activity** — one workout, attached to a DailyLog
```
- daily_log       FK to DailyLog (CASCADE)
- name_of_activity   CharField (e.g. "Easy Swim Intervals")
- activity_type   choice from: Run, Walk, Hike, Bike, Mountain Bike, Yoga, Sport, Lift, Swim, Other
- duration_min    PositiveIntegerField
- rpe             Decimal 0–10 (Rate of Perceived Exertion, validators enforced, nullable)
- distance        Float (nullable)
- distance_unit   choice: Miles, Kilometers, Meters, Yards
- notes           TextField
- created_at      auto timestamp
```

### URL map
```
/                              → landing page (pages app)
/accounts/login                → login
/accounts/signup               → signup
/accounts/logout               → logout
/dashboard/                    → main dashboard (7-day overview)
/dashboard/activity-summary/   → activity summary detail
/dashboard/training-load/      → training load detail
/dashboard/wellness-stress/    → wellness vs stress detail
/dashboard/sleep-score/        → sleep score detail
/logs/                         → list of all daily logs
/logs/new/                     → create a new daily log
/logs/<id>/activity/new/       → add an activity to a log
/logs/<id>/delete/             → delete a log
/history/                      → all activities ever (Strava-style table)
/tomorrow/                     → tomorrow's workout plan
```

---

## 3. Calculations and Algorithms (the technical heart)

This is the most important section for the presentation. Every formula and decision rule is explicit.

### 3.1 Sleep Score (0–100)

Calculated for any DailyLog from two inputs: `sleep_hours` and `sleep_quality` (1–10).

```
duration_score = min((sleep_hours / 9) × 100, 100)     # caps at 100
quality_score  = (sleep_quality / 10) × 100
sleep_score    = round(duration_score × 0.6 + quality_score × 0.4)
```

**Why the weights?**
Sleep duration is weighted **60%** — it's the most reliable predictor of recovery. Subjective quality is weighted **40%** — it captures things like restlessness, wake-ups, and how rested the user feels.

**Why divide hours by 9?** 9 hours is treated as the "perfect night" target for athletes. Anything ≥ 9 caps at 100 (we don't reward over-sleeping past that).

**Where is it used?**
- Dashboard "Sleep Score" card (gauge, 7-day average)
- Detail page (gauge + 30-day trend charts for hours and quality separately)
- Daily Logs list (per-night sleep score badge)

---

### 3.2 Recovery Score (per day)

Tracks how recovered the user is on a single day.

```
recovery_score = sleep_quality + wellness − stress
```

Theoretical range: −10 (worst) to +20 (best). In practice usually 0–15.

**Why subtract stress?** Stress drains recovery. High stress + good sleep can still leave the athlete depleted, and the formula reflects that with a direct subtraction.

**Where is it used?**
- Wellness vs Stress detail page → 30-day line chart of recovery score
- 30-day average displayed at top of recovery chart

---

### 3.3 Training Load

A standard sport-science metric, computed per activity.

```
activity_load = duration_min × rpe
weekly_load   = sum of (duration_min × rpe) over the week
avg_daily_load = weekly_load / 7
```

**Zones** (avg daily load):
| Zone | Range | Color |
|---|---|---|
| Low | 0–300 | Green |
| Moderate | 300–600 | Yellow |
| High | 600–900 | Orange |
| Overreaching | 900–1200+ | Red |

The dashboard renders a horizontal gauge bar with a black dot positioned at `(avg_daily_load / 1200) × 100%` along a green→red gradient.

**Detail page extras:**
- 4-week comparison (Mon–Sun aligned weeks, oldest to newest)
- Per-activity breakdown for the current week, showing each activity's individual load and a horizontal bar for visual comparison

---

### 3.4 Activity Summary metrics

For the 7-day window:
```
total_activity_minutes = sum(duration_min) across all activities
total_hours = total_minutes // 60
remaining_minutes = total_minutes % 60
activity_count = count of all activities
```

For the type breakdown:
```
Group activities by activity_type, count and sum minutes per type.
Bar percentage = (type_total_mins / max_type_mins) × 100
```

For the 4-week trend:
```
Find this Monday: today - timedelta(days=today.weekday())
For each of last 4 weeks (oldest first), sum activity minutes
Each bar's percent = (week_total / max_week_total) × 100
```

---

### 3.5 Tomorrow's Plan Algorithm (the centerpiece)

This is the most complex feature. It produces:
1. An **intensity zone** (Rest / Recovery / Easy / Moderate / Hard)
2. An **RPE range** (e.g. RPE 4–5)
3. **Up to 3 suggested workouts** with activity-specific durations

#### Step 1 — Find the "anchor day"
The anchor is the day whose data drives the recommendation most heavily.

```
if a DailyLog exists for today:
    anchor_log = today's log
    has_today_log = True
else:
    anchor_log = yesterday's log (if it exists)
    has_today_log = False  → page shows a yellow "log today for the most accurate recommendation" banner
```

#### Step 2 — Pull a 7-day window of logs
```
week_start = today − 6 days
logs_7 = all DailyLogs in [week_start, today]
```

#### Step 3 — Detect rest day (override everything)
Rest day is triggered if EITHER:
- **Trigger A:** anchor_log.sleep_hours < 2 hours
- **Trigger B:** Sum of `duration_min` for activities on the anchor day where `RPE >= 9` totals **≥ 120 minutes**

If rest_day is True → zone = "REST" and skip to step 6.

#### Step 4 — Compute anchor day load
```
yesterday_rpe_avg     = mean RPE of anchor activities (0 if none)
yesterday_duration    = sum of duration_min for anchor activities
yesterday_high_effort = (yesterday_rpe_avg ≥ 8) OR (yesterday_duration ≥ 90 min)
```

#### Step 5 — Compute 7-day sleep averages
```
sleep_hours_list   = [log.sleep_hours for log in logs_7 if not None]
sleep_quality_list = [log.sleep_quality for log in logs_7 if not None]

avg_sleep_hours   = mean(sleep_hours_list)   or None
avg_sleep_quality = mean(sleep_quality_list) or None

bad_sleep_7  = (avg_sleep_hours < 6) OR (avg_sleep_quality < 5)
good_sleep_7 = (avg_sleep_hours > 7.5) AND (avg_sleep_quality > 7)
```

Days where data is missing are excluded from the average — important so blank fields don't drag the mean toward zero.

#### Step 6 — Pick the intensity zone (priority order, first match wins)
| Priority | Zone | Trigger |
|---|---|---|
| 1 | **REST** | rest_day is True |
| 2 | **RECOVERY** | yesterday_high_effort is True |
| 3 | **EASY** | bad_sleep_7 is True |
| 4 | **HARD** | good_sleep_7 AND yesterday_rpe_avg ≤ 4 |
| 5 | **MODERATE** | default — no other rule fired |

RPE ranges per zone:
| Zone | RPE |
|---|---|
| Recovery | 1–3 |
| Easy | 4–5 |
| Moderate | 6–7 |
| Hard | 8–9 |
| Rest | none (no workout suggested) |

#### Step 7 — Compute base duration (the user's normal training time)
```
For each day in last 7 days:
    daily_total = sum(activity.duration_min)
    if daily_total > 0:
        add to daily_durations list   # rest days excluded
base_duration = round(mean(daily_durations))
                or 30 if user has no activity history at all
```

Excluding zero-activity days prevents rest days from dragging down what is meant to represent the user's *typical* workout length.

#### Step 8 — Apply the zone multiplier to get the global duration range
| Zone | Low × | High × |
|---|---|---|
| Recovery | 0.40 | 0.55 |
| Easy | 0.60 | 0.75 |
| Moderate | 0.90 | 1.10 |
| Hard | 1.10 | 1.30 |

```
dur_low  = round(base_duration × low_multiplier  / 5) × 5  # round to 5 min
dur_high = round(base_duration × high_multiplier / 5) × 5
if dur_low == dur_high:
    dur_high = dur_low + 5    # always show a real range, not a single number
```

#### Step 9 — Pick the 3 suggested workouts

There are three branches:

**Branch A: REST day**
Hard-coded list of recovery activities (no history query):
```
[
  { name: "Walk",    low: 20, high: 30 },
  { name: "Stretch", low: 15, high: 20 },
  { name: "Yoga",    low: 25, high: 30 },
]
```

**Branch B: Has activity history in last 30 days**
```
top_types = (
    Activity.objects
    .filter(daily_log__user=user, daily_log__date >= today−29 days)
    .values("activity_type")
    .annotate(count=Count("id"))
    .order_by("-count", "activity_type")    # most-logged first, alphabetical tiebreak
    [:3]                                    # take top 3
)
```
This is a single SQL query that groups, counts, sorts, and limits server-side.

For each top type, scale the duration with an **activity-specific multiplier**:
| Activity | Multiplier | Why |
|---|---|---|
| Run | 1.00 | Baseline |
| Walk | 1.10 | Lower intensity, slightly longer |
| Hike | 1.30 | Long-duration aerobic activity |
| Bike | 1.30 | Long-duration aerobic activity |
| Mountain Bike | 1.20 | Long but more intense than road bike |
| Swim | 0.50 | Highly intense per minute, much shorter |
| Lift | 0.80 | Shorter focused sessions |
| Yoga | 0.85 | Focused medium length |
| Sport | 1.00 | Baseline |
| Other | 1.00 | Baseline |

```
for activity_type in top_types:
    multiplier = ACTIVITY_DURATION_MULT[activity_type]
    new_low  = max(5, round(dur_low  × multiplier / 5) × 5)
    new_high = round(dur_high × multiplier / 5) × 5
    if new_high <= new_low:
        new_high = new_low + 5
    suggestions.append({ name, low, high })
```

**Branch C: No activity history**
Single fallback card with the unmodified zone duration:
```
[
  { name: "{ZoneLabel} Workout", low: dur_low, high: dur_high }
]
```
e.g. `Easy Workout — 35–45 min`.

#### Visual output
- Top: color-coded intensity card (gray = Rest, green = Recovery, blue = Easy, orange = Moderate, red = Hard) showing zone label + RPE range
- Middle: up to 3 white cards in a flex row, each with a colored top stripe matching the zone, showing activity name and duration range
- Bottom: 3 stat boxes — 7-day avg sleep hours, avg sleep quality, avg workout duration

---

### 3.6 Chart rendering algorithm (server-side SVG)

All line charts are rendered without any JavaScript library. Python computes the SVG coordinates and ticks, then passes them to the template which loops over them.

#### Computing polyline points
```python
def _svg_points(data_list, value_key, chart_width, chart_height,
                pad_left, pad_right, pad_top, pad_bottom, max_val=None):
    plot_width  = chart_width  − pad_left − pad_right
    plot_height = chart_height − pad_top  − pad_bottom
    if max_val is None:
        max_val = max(value at value_key across all items) or 1

    for idx, item in enumerate(data_list):
        x = pad_left + (plot_width × idx / (count − 1))
        y = pad_top  + ((max_val − item[value_key]) / max_val) × plot_height
        item.x, item.y = round(x), round(y)
```

The Y inversion `(max_val − value)` flips the coordinate space because in SVG, y=0 is at the **top**, but in a chart we want the *highest value* at the top.

#### Y-axis ticks
```python
def _y_ticks(max_val, num_ticks=4, ...):
    plot_height = chart_height − pad_top − pad_bottom
    for i in range(num_ticks + 1):
        value = max_val × i / num_ticks
        y     = pad_top + ((max_val − value) / max_val) × plot_height
        ticks.append({ "y": y, "label": display_value })
```

#### Nice-rounding the axis max
Raw data max might be `8.7`, which would create ugly ticks (0, 2.175, 4.35, ...). The `_nice_max()` helper rounds up to a clean number:
```
nice_options = [1, 2, 3, 5, 8, 10, 12, 15, 20, 25, 30, 50, 75, 100]
return the smallest option ≥ raw_max
```
So a raw max of 8.7 becomes 10, and ticks become 0, 2.5, 5, 7.5, 10.

Both the polyline points and the Y-axis ticks share this same `max_val` so they're guaranteed to line up visually.

---

## 4. Frontend / UI

### Design system
- **Background:** Mountain photo (`static/images/random_bg.jpg`), fixed-attached
- **Sidebar:** Black (`#111`) with white text — Dashboard / Daily Logs / Tomorrow Plan / History / Logout
- **Cards:** Translucent gray (`rgba(130, 130, 130, 0.93)`) with subtle drop shadow
- **Typography:** Sans-serif system font, black text on light cards, white on dark headers
- **Headers:** Translucent black banners (`rgba(1, 13, 16, 0.55)`) so the title stands out against any background

### Color palette (consistent across all pages)
| Color | Hex | Used for |
|---|---|---|
| Recovery / "good" | `#2e7d32` | Green |
| Easy / "Wellness" | `#1565c0` | Blue |
| Moderate | `#e65100` | Orange |
| Hard / "Stress" | `#b71c1c` | Red |
| Rest | `#757575` | Gray |
| Recovery score line | `#00e676` | Vibrant green |
| Sleep duration line | `#0b6cff` | Blue |
| Sleep quality line | `#9c27b0` | Purple |

Activity type badges on the History page also follow this palette (Run/Walk/Hike = blue, Bike = green, Swim = cyan, Lift = red, Yoga = purple, Sport = orange).

### Pages

**Dashboard** (`/dashboard/`)
- 4 clickable metric cards in a 2×2 grid
- Each card shows a 7-day summary with a small chart inside
- Hovering lifts the card slightly (`transform: translateY(-11px)`)

**Detail pages** (one per metric — Activity Summary / Training Load / Sleep Score / Wellness vs Stress)
- Each has the same structure: dark header banner, "← Back to Dashboard" link below it, then 2–4 section cards
- Sleep Score: semicircle gauge, 7-day avg stats, best/worst nights grid, 30-day SVG line charts for hours & quality (with Y-axis ticks and dashed gridlines)
- Wellness vs Stress: 7-day side-by-side bars (wellness blue + stress red), 30-day recovery score SVG line chart, 30-day averages
- Training Load: load gauge bar with zone badge, 4-week comparison bars, per-activity load breakdown
- Activity Summary: 7-day stats, daily bar chart, type breakdown bars, full activity table with RPE color dots, 4-week trend bars

**Daily Logs** (`/logs/`)
- List of all logs newest-first
- Each card: date, sleep score badge (right side), sleep/quality/wellness/stress stats, attached activities, "Add activity" and "Delete log" buttons
- "+ New Daily Log" button to create one
- New log form uses a native browser date picker (`<input type="date">`)

**Tomorrow's Plan** (`/tomorrow/`)
- See section 3.5 above for full UI breakdown

**History** (`/history/`)
- Strava-style table of all activities ever logged
- Columns: Date / Activity (with type badge) / Distance / Duration / RPE (with colored dot for intensity)
- Summary bar at top: total activity count + date range

---

## 5. Forms and Validation

### DailyLogForm
Fields: `date`, `sleep_hours`, `sleep_quality`, `wellness`, `stress`, `notes`
- Date field uses `<input type="date">` widget for native browser calendar
- Sleep quality / wellness / stress validated 0–10 by `MinValueValidator` and `MaxValueValidator` at the model level — the form rejects out-of-range values with an error message before saving
- Sleep hours stored as `Decimal` with 1 decimal place
- Unique-per-(user, date) constraint prevents duplicates; trying to create a duplicate shows "You already have a log for this date."

### ActivityForm
Fields: `name_of_activity`, `activity_type`, `duration_min`, `distance`, `distance_unit`, `rpe`, `notes`
- RPE stored as `Decimal` (1 decimal place) so users can log fractional values like 7.5
- Activity type is a fixed choice list

---

## 6. Performance considerations

Even though this is a small app, the views were written with N+1 query prevention in mind:

- **`select_related("daily_log")`** in the History view — fetches the related DailyLog in the same SQL query so iterating over activities doesn't trigger a separate query per row
- **`prefetch_related("activities")`** in the daily logs and tomorrow views — pre-fetches all activities for the displayed logs in one extra query rather than one per log
- **`.aggregate(Sum(...))`** — totals are computed in SQL, not in Python loops
- **`.values("field").annotate(count=Count("id"))`** — grouping and counting (used for top activity types in the tomorrow view) is delegated to SQL
- **`ExpressionWrapper(F("duration_min") × F("rpe"))`** — training load is computed in the database via SQL expressions, not in Python

---

## 7. Authentication and security

- Every view uses the `@login_required` decorator — unauthenticated users are redirected to `/accounts/login`
- All queries scoped by `user=request.user` — users can never see another user's data
- Django's CSRF middleware is enabled — all forms include `{% csrf_token %}`
- Passwords validated by Django's full validator stack: similarity, minimum length, common-password blocklist, numeric-only blocklist
- Logout uses POST (not GET) to prevent CSRF-based logout attacks

---

## 8. Time-zone handling

- `TIME_ZONE = 'America/Los_Angeles'` in settings
- `USE_TZ = True` so timestamps are stored in UTC and converted on display
- Views use `timezone.localdate()` instead of `date.today()` so "today" always reflects the user's local date — prevents the bug where a 7pm PT log was being attributed to the next day in UTC

---

## 9. Tomorrow Plan Logic — Worked Examples

### Example 1 — Healthy moderate athlete
- 7-day avg sleep: 7.4h, quality 7
- Yesterday: 45 min run, RPE 6
- Top 30-day activities: Run (15), Bike (8), Lift (3)

→ rest_day = False
→ yesterday_high_effort = False (6 < 8 and 45 < 90)
→ bad_sleep_7 = False
→ good_sleep_7 = False (quality 7 not > 7)
→ Zone = **MODERATE** (RPE 6–7)
→ base_duration ~50 min, dur_low/high = 45–55 min
→ Suggestions:
  - Run: 45–55 min
  - Bike: 60–70 min (50 × 1.30 = 65, scaled around it)
  - Lift: 35–45 min (50 × 0.80 = 40)

### Example 2 — Hard effort yesterday
- Yesterday: 90 min run, RPE 8
- Sleep avg good

→ yesterday_high_effort = True (8 ≥ 8 OR 90 ≥ 90)
→ Zone = **RECOVERY** (RPE 1–3)
→ Multipliers 0.40–0.55 of base
→ Suggestions: light versions of Run / Bike / Lift

### Example 3 — Bad sleep, normal day
- 7-day avg sleep 5.4h
- Yesterday: 30 min easy walk

→ rest_day = False
→ yesterday_high_effort = False
→ bad_sleep_7 = True (5.4 < 6)
→ Zone = **EASY** (RPE 4–5)

### Example 4 — Forced rest
- Yesterday: 80 min run RPE 9 + 50 min cross-train RPE 9 → 130 min at RPE 9+

→ Trigger B fires → rest_day = True
→ Zone = **REST**
→ Suggestions: Walk 20–30 min, Stretch 15–20 min, Yoga 25–30 min

---

## 10. Project file structure

```
athletic_insight/
├── config/                  # Django project settings
│   ├── settings.py          # TIME_ZONE, INSTALLED_APPS, etc.
│   └── urls.py              # Root URL conf
├── pages/                   # Landing page
├── accounts/                # Signup, auth redirects
├── workouts/                # Core data app
│   ├── models.py            # DailyLog, Activity, sleep_score property
│   ├── views.py             # logs_view, log_create, activity_add, history_view, tomorrow_view (with full algorithm)
│   ├── forms.py             # DailyLogForm (date picker), ActivityForm
│   └── urls.py
├── dashboard/               # Dashboard + 4 detail pages
│   ├── views.py             # All metric calculations + SVG helper functions (_svg_points, _y_ticks, _nice_max)
│   └── urls.py
├── templates/
│   ├── base.html            # Sidebar layout
│   ├── dashboard/           # 5 dashboard templates
│   ├── workouts/            # logs.html, log_create.html, activity_add.html, tomorrow.html, history.html
│   ├── accounts/signup.html
│   └── registration/login.html
├── static/images/           # Background image
├── db.sqlite3
└── manage.py
```

---

## 11. Highlights for the presentation

### Most impressive technical pieces
1. **Tomorrow's Plan algorithm** — multi-stage decision tree combining recovery state and historical training data
2. **Server-rendered SVG charts** — all charts produced without JavaScript by computing coordinates and ticks in Python
3. **Per-activity duration scaling** — recognizes that a 50-min swim is a much harder workout than a 50-min walk
4. **Database-side aggregations** — uses Django's `Count`, `Sum`, `F`, `ExpressionWrapper` to keep heavy lifting in SQL rather than Python
5. **Proper handling of missing data** — averages always exclude unlogged days so a blank field never gets counted as zero

### Business / product angle
- Personalized recommendations based on individual data, not generic plans
- Combines objective (load) and subjective (recovery) signals — most apps only do one
- Zero JavaScript dependencies — fast first paint and no client-side framework overhead
- Single-user focused (vs social/comparison features) — designed as a personal training journal

### Future roadmap
- v3: workout-specific suggestions ("interval run" vs "easy run")
- Test suite for views and the recommendation algorithm
- Day-of-week patterns (rest-day prediction)
- Export workouts to a calendar app

---

## 12. Key formulas — quick reference card

| Metric | Formula |
|---|---|
| Sleep score | `round(min(sleep_hours/9 × 100, 100) × 0.6 + (sleep_quality/10 × 100) × 0.4)` |
| Recovery score | `sleep_quality + wellness − stress` |
| Activity load | `duration_min × rpe` |
| Training load (week) | `Σ duration_min × rpe` over 7 days |
| Avg daily load | `weekly_load / 7` |
| Tomorrow base duration | `mean(daily totals over last 7 days, excluding zero-activity days)` |
| Tomorrow zone duration | `base_duration × zone_multiplier`, rounded to nearest 5 min |
| Tomorrow per-activity duration | `zone_duration × activity_multiplier`, rounded to nearest 5 min |
| Top 3 activities | `Activity.filter(last 30 days).values(type).annotate(count).order_by(-count, type)[:3]` |
| Sleep score gauge degrees | `(sleep_score / 100) × 180°` |
| Load gauge percent | `min((avg_daily_load / 1200) × 100, 100)` |

---

*End of brief. Source code lives in `/Users/jakebowen/Desktop/athletic_insight`. Every value, calculation, and decision rule above maps to actual lines in `workouts/views.py`, `dashboard/views.py`, and `workouts/models.py`.*
