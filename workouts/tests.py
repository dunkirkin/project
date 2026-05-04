from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import Client, TestCase
from django.urls import reverse

from .models import Activity, DailyLog
from .views import ACTIVITY_DURATION_MULT, _scale_duration


# ──────────────────────────────────────────────────────────────
#  MODEL TESTS
# ──────────────────────────────────────────────────────────────

class SleepScoreTest(TestCase):
    """Tests for the DailyLog.sleep_score property."""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="pass")
        self.today = date.today()

    def _make_log(self, sleep_hours, sleep_quality):
        return DailyLog(
            user=self.user,
            date=self.today,
            sleep_hours=sleep_hours,
            sleep_quality=sleep_quality,
        )

    def test_perfect_sleep_score(self):
        """9 hours + quality 10 → score of 100."""
        log = self._make_log(sleep_hours=9, sleep_quality=10)
        self.assertEqual(log.sleep_score, 100)

    def test_no_sleep_data_returns_none(self):
        """No sleep hours or quality → sleep_score is None."""
        log = self._make_log(sleep_hours=None, sleep_quality=None)
        self.assertIsNone(log.sleep_score)

    def test_sleep_hours_capped_at_100(self):
        """More than 9 hours still caps at 100% for the duration component."""
        log = self._make_log(sleep_hours=12, sleep_quality=10)
        self.assertEqual(log.sleep_score, 100)

    def test_typical_sleep_score(self):
        """7.5 hours + quality 8 → (7.5/9*100)*0.6 + (8/10*100)*0.4 = 50 + 32 = 82."""
        log = self._make_log(sleep_hours=Decimal("7.5"), sleep_quality=Decimal("8"))
        self.assertEqual(log.sleep_score, 82)

    def test_zero_values_return_none(self):
        """Both 0 are treated as no data (falsy) → sleep_score returns None."""
        log = self._make_log(sleep_hours=0, sleep_quality=0)
        self.assertIsNone(log.sleep_score)


class RecoveryScoreTest(TestCase):
    """Tests for the recovery score formula: sleep_quality + wellness - stress."""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser2", password="pass")
        self.today = date.today()

    def _make_log(self, sleep_quality, wellness, stress):
        return DailyLog.objects.create(
            user=self.user,
            date=self.today,
            sleep_quality=sleep_quality,
            wellness=wellness,
            stress=stress,
        )

    def test_maximum_recovery_score(self):
        """sleep_quality=10, wellness=10, stress=0 → recovery = +20."""
        log = self._make_log(10, 10, 0)
        self.assertEqual(float(log.sleep_quality) + float(log.wellness) - float(log.stress), 20)

    def test_minimum_recovery_score(self):
        """sleep_quality=0, wellness=0, stress=10 → recovery = -10."""
        log = self._make_log(0, 0, 10)
        self.assertEqual(float(log.sleep_quality) + float(log.wellness) - float(log.stress), -10)

    def test_typical_recovery_score(self):
        """sleep_quality=7, wellness=8, stress=3 → recovery = 12."""
        log = self._make_log(7, 8, 3)
        self.assertEqual(float(log.sleep_quality) + float(log.wellness) - float(log.stress), 12)


class ValidatorTest(TestCase):
    """Tests that model validators enforce 0–10 for wellness fields and 0–10 for RPE."""

    def setUp(self):
        self.user = User.objects.create_user(username="validator_user", password="pass")
        self.today = date.today()

    def test_sleep_quality_above_10_is_invalid(self):
        log = DailyLog(
            user=self.user, date=self.today,
            sleep_quality=11, wellness=5, stress=5
        )
        with self.assertRaises(ValidationError):
            log.full_clean()

    def test_wellness_below_0_is_invalid(self):
        log = DailyLog(
            user=self.user, date=self.today,
            sleep_quality=5, wellness=-1, stress=5
        )
        with self.assertRaises(ValidationError):
            log.full_clean()

    def test_stress_exactly_10_is_valid(self):
        log = DailyLog(
            user=self.user, date=self.today,
            sleep_quality=5, wellness=5, stress=10
        )
        try:
            log.full_clean()
        except ValidationError:
            self.fail("stress=10 should be valid but raised ValidationError")

    def test_rpe_above_10_is_invalid(self):
        log = DailyLog.objects.create(user=self.user, date=self.today)
        activity = Activity(
            daily_log=log, activity_type="Run",
            duration_min=30, rpe=Decimal("11")
        )
        with self.assertRaises(ValidationError):
            activity.full_clean()

    def test_rpe_decimal_is_valid(self):
        """RPE of 7.5 (decimal) should be accepted."""
        log = DailyLog.objects.create(user=self.user, date=self.today)
        activity = Activity(
            daily_log=log, activity_type="Run", name_of_activity="Morning Run",
            duration_min=30, rpe=Decimal("7.5")
        )
        try:
            activity.full_clean()
        except ValidationError:
            self.fail("rpe=7.5 should be valid but raised ValidationError")


class DurationScalingTest(TestCase):
    """Tests for the _scale_duration helper and ACTIVITY_DURATION_MULT values."""

    def test_swim_is_half(self):
        """Swim multiplier is 0.5 — should return roughly half the base duration."""
        self.assertEqual(ACTIVITY_DURATION_MULT["Swim"], 0.5)

    def test_bike_multiplier(self):
        self.assertEqual(ACTIVITY_DURATION_MULT["Bike"], 1.30)

    def test_lift_multiplier(self):
        self.assertEqual(ACTIVITY_DURATION_MULT["Lift"], 0.80)

    def test_scale_duration_swim_rounds_to_5(self):
        """60–80 min base × 0.5 → 30–40 min, both multiples of 5."""
        low, high = _scale_duration("Swim", 60, 80)
        self.assertEqual(low % 5, 0)
        self.assertEqual(high % 5, 0)
        self.assertLess(low, high)

    def test_scale_duration_high_never_equals_low(self):
        """high must always be greater than low."""
        for atype in ACTIVITY_DURATION_MULT:
            low, high = _scale_duration(atype, 30, 30)
            self.assertGreater(high, low, msg=f"Failed for activity type: {atype}")

    def test_unknown_activity_type_defaults_to_1x(self):
        """An unrecognized activity type defaults to 1.0 multiplier."""
        low, high = _scale_duration("Unknown", 60, 80)
        self.assertEqual(low, 60)
        self.assertEqual(high, 80)


# ──────────────────────────────────────────────────────────────
#  FORM TESTS
# ──────────────────────────────────────────────────────────────

class DailyLogFormTest(TestCase):
    """Tests that DailyLogForm validates input correctly."""

    def _form(self, **kwargs):
        from .forms import DailyLogForm
        data = {
            "date": str(date.today()),
            "sleep_hours": "7.5",
            "sleep_quality": "8",
            "wellness": "7",
            "stress": "3",
            "notes": "",
        }
        data.update(kwargs)
        return DailyLogForm(data=data)

    def test_valid_form(self):
        self.assertTrue(self._form().is_valid())

    def test_sleep_quality_above_10_invalid(self):
        form = self._form(sleep_quality="11")
        self.assertFalse(form.is_valid())
        self.assertIn("sleep_quality", form.errors)

    def test_wellness_below_0_invalid(self):
        form = self._form(wellness="-1")
        self.assertFalse(form.is_valid())
        self.assertIn("wellness", form.errors)

    def test_missing_date_invalid(self):
        form = self._form(date="")
        self.assertFalse(form.is_valid())
        self.assertIn("date", form.errors)


class ActivityFormTest(TestCase):
    """Tests that ActivityForm validates RPE and required fields."""

    def _form(self, **kwargs):
        from .forms import ActivityForm
        data = {
            "name_of_activity": "Morning Run",
            "activity_type": "Run",
            "duration_min": "45",
            "rpe": "7.5",
            "distance": "5",
            "distance_unit": "Miles",
            "notes": "",
        }
        data.update(kwargs)
        return ActivityForm(data=data)

    def test_valid_form(self):
        self.assertTrue(self._form().is_valid())

    def test_decimal_rpe_accepted(self):
        self.assertTrue(self._form(rpe="6.5").is_valid())

    def test_rpe_above_10_invalid(self):
        form = self._form(rpe="11")
        self.assertFalse(form.is_valid())
        self.assertIn("rpe", form.errors)

    def test_missing_activity_type_invalid(self):
        form = self._form(activity_type="")
        self.assertFalse(form.is_valid())


# ──────────────────────────────────────────────────────────────
#  VIEW TESTS (authentication + status codes)
# ──────────────────────────────────────────────────────────────

class AuthRedirectTest(TestCase):
    """Unauthenticated users should be redirected to login for all protected views."""

    PROTECTED_URLS = [
        "/logs/",
        "/history/",
        "/tomorrow/",
        "/logs/new/",
        "/dashboard/",
        "/dashboard/activity-summary/",
        "/dashboard/training-load/",
        "/dashboard/wellness-stress/",
        "/dashboard/sleep-score/",
    ]

    def test_redirects_to_login(self):
        client = Client()
        for url in self.PROTECTED_URLS:
            response = client.get(url)
            self.assertIn(
                response.status_code, [301, 302],
                msg=f"{url} should redirect unauthenticated user"
            )


class LoggedInViewTest(TestCase):
    """Logged-in users should get 200 OK on all main views."""

    def setUp(self):
        self.user = User.objects.create_user(username="viewuser", password="pass")
        self.client.login(username="viewuser", password="pass")

    def test_logs_view(self):
        response = self.client.get(reverse("logs"))
        self.assertEqual(response.status_code, 200)

    def test_log_create_view(self):
        response = self.client.get(reverse("log_create"))
        self.assertEqual(response.status_code, 200)

    def test_history_view(self):
        response = self.client.get(reverse("history"))
        self.assertEqual(response.status_code, 200)

    def test_tomorrow_view(self):
        response = self.client.get(reverse("tomorrow"))
        self.assertEqual(response.status_code, 200)

    def test_dashboard_view(self):
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)

    def test_activity_summary_view(self):
        response = self.client.get(reverse("activity_summary"))
        self.assertEqual(response.status_code, 200)

    def test_training_load_view(self):
        response = self.client.get(reverse("training_load"))
        self.assertEqual(response.status_code, 200)

    def test_wellness_stress_view(self):
        response = self.client.get(reverse("wellness_stress"))
        self.assertEqual(response.status_code, 200)

    def test_sleep_score_view(self):
        response = self.client.get(reverse("sleep_score"))
        self.assertEqual(response.status_code, 200)


# ──────────────────────────────────────────────────────────────
#  TOMORROW'S PLAN ALGORITHM TESTS
# ──────────────────────────────────────────────────────────────

class TomorrowPlanZoneTest(TestCase):
    """
    Tests the zone-selection logic of tomorrow_view by creating realistic
    log data and checking what zone the view assigns in its context.
    """

    def setUp(self):
        self.user = User.objects.create_user(username="planuser", password="pass")
        self.client.login(username="planuser", password="pass")
        self.today = date.today()

    def _create_log(self, days_ago=0, sleep_hours=7, sleep_quality=7,
                    wellness=7, stress=3, activities=None):
        log_date = self.today - timedelta(days=days_ago)
        log = DailyLog.objects.create(
            user=self.user,
            date=log_date,
            sleep_hours=Decimal(str(sleep_hours)),
            sleep_quality=Decimal(str(sleep_quality)),
            wellness=Decimal(str(wellness)),
            stress=Decimal(str(stress)),
        )
        for act in (activities or []):
            Activity.objects.create(
                daily_log=log,
                activity_type=act.get("type", "Run"),
                name_of_activity=act.get("name", "Run"),
                duration_min=act.get("duration", 45),
                rpe=Decimal(str(act.get("rpe", 5))),
            )
        return log

    def _get_zone(self):
        response = self.client.get(reverse("tomorrow"))
        self.assertEqual(response.status_code, 200)
        return response.context["zone"]

    def test_rest_day_triggered_by_low_sleep(self):
        """Anchor day with < 2 hours sleep → REST zone."""
        self._create_log(days_ago=0, sleep_hours=1.5)
        self.assertEqual(self._get_zone(), "REST")

    def test_rest_day_triggered_by_very_high_rpe(self):
        """120+ minutes at RPE 9+ on anchor day → REST zone."""
        self._create_log(
            days_ago=0,
            activities=[
                {"type": "Run", "name": "Long Hard Run", "duration": 130, "rpe": 9},
            ]
        )
        self.assertEqual(self._get_zone(), "REST")

    def test_recovery_zone_after_hard_effort(self):
        """Avg RPE ≥ 8 on anchor day → RECOVERY zone (no rest triggers)."""
        self._create_log(
            days_ago=0,
            sleep_hours=7,
            activities=[
                {"type": "Run", "name": "Hard Run", "duration": 50, "rpe": 8},
            ]
        )
        self.assertEqual(self._get_zone(), "RECOVERY")

    def test_easy_zone_from_bad_sleep(self):
        """7-day avg sleep < 6 hours → EASY zone (no harder triggers)."""
        for i in range(7):
            self._create_log(days_ago=i, sleep_hours=5, sleep_quality=4, wellness=6, stress=4)
        self.assertEqual(self._get_zone(), "EASY")

    def test_hard_zone_conditions(self):
        """Good 7-day sleep (>7.5h, quality >7) + yesterday low RPE (≤4) → HARD zone."""
        for i in range(7):
            self._create_log(
                days_ago=i,
                sleep_hours=8,
                sleep_quality=8,
                wellness=9,
                stress=2,
                activities=[{"type": "Run", "name": "Easy Run", "duration": 30, "rpe": 3}],
            )
        self.assertEqual(self._get_zone(), "HARD")

    def test_no_data_defaults_to_moderate(self):
        """No logs at all → MODERATE (default fallback)."""
        self.assertEqual(self._get_zone(), "MODERATE")

    def test_three_suggestions_returned(self):
        """With activity history, tomorrow view returns exactly 3 suggestion cards."""
        for i in range(7):
            self._create_log(
                days_ago=i,
                activities=[
                    {"type": "Run",  "name": "Run",  "duration": 40, "rpe": 5},
                    {"type": "Bike", "name": "Bike", "duration": 60, "rpe": 5},
                    {"type": "Swim", "name": "Swim", "duration": 30, "rpe": 5},
                ]
            )
        response = self.client.get(reverse("tomorrow"))
        self.assertEqual(len(response.context["suggestions"]), 3)

    def test_duplicate_date_log_rejected(self):
        """Creating two logs for the same date should fail."""
        self._create_log(days_ago=0)
        with self.assertRaises(Exception):
            self._create_log(days_ago=0)
