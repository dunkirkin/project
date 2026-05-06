from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import Client, TestCase
from django.urls import reverse

from .models import Activity, DailyLog
from .views import ACTIVITY_DURATION_MULT, _scale_duration

# Test cases for the models and the correct algorihtim scores


class SleepScoreTest(TestCase):
    # Tests for the DailyLog.sleep_score property

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
        # 9 hours + quality 10 → score of 100
        log = self._make_log(sleep_hours=9, sleep_quality=10)
        self.assertEqual(log.sleep_score, 100)

    def test_no_sleep_data_returns_none(self):
        # No sleep hours or quality → sleep_score is None
        log = self._make_log(sleep_hours=None, sleep_quality=None)
        self.assertIsNone(log.sleep_score)

    def test_sleep_hours_capped_at_100(self):
        # More than 9 hours still caps at 100% for the duration component
        log = self._make_log(sleep_hours=12, sleep_quality=10)
        self.assertEqual(log.sleep_score, 100)

    def test_typical_sleep_score(self):
        # 7.5 hours + quality 8 → (7.5/9*100)*0.6 + (8/10*100)*0.4 = 50 + 32 = 82
        log = self._make_log(sleep_hours=Decimal("7.5"), sleep_quality=Decimal("8"))
        self.assertEqual(log.sleep_score, 82)

    def test_zero_values_return_none(self):
        # Both 0 are treated as no data (falsy) → sleep_score returns None
        log = self._make_log(sleep_hours=0, sleep_quality=0)
        self.assertIsNone(log.sleep_score)


class RecoveryScoreTest(TestCase):
    # Tests for the recovery score formula: sleep_quality + wellness - stress

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
        # sleep_quality=10, wellness=10, stress=0 → recovery = +20
        log = self._make_log(10, 10, 0)
        self.assertEqual(float(log.sleep_quality) + float(log.wellness) - float(log.stress), 20)

    def test_minimum_recovery_score(self):
        # sleep_quality=0, wellness=0, stress=10 → recovery = -10
        log = self._make_log(0, 0, 10)
        self.assertEqual(float(log.sleep_quality) + float(log.wellness) - float(log.stress), -10)

    def test_typical_recovery_score(self):
        # sleep_quality=7, wellness=8, stress=3 → recovery = 12
        log = self._make_log(7, 8, 3)
        self.assertEqual(float(log.sleep_quality) + float(log.wellness) - float(log.stress), 12)


class ValidatorTest(TestCase):
    # Tests that model validators enforce 0-10 for wellness fields and 0-10 for RPE

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
        # RPE of 7.5 (decimal) should be accepted
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
    # Tests for the _scale_duration helper and ACTIVITY_DURATION_MULT values

    def test_swim_is_half(self):
        # Swim multiplier is 0.5 — should return roughly half the base duration
        self.assertEqual(ACTIVITY_DURATION_MULT["Swim"], 0.5)

    def test_bike_multiplier(self):
        self.assertEqual(ACTIVITY_DURATION_MULT["Bike"], 1.30)

    def test_lift_multiplier(self):
        self.assertEqual(ACTIVITY_DURATION_MULT["Lift"], 0.80)

    def test_scale_duration_swim_rounds_to_5(self):
        # 60-80 min base x 0.5 → 30-40 min, both multiples of 5
        low, high = _scale_duration("Swim", 60, 80)
        self.assertEqual(low % 5, 0)
        self.assertEqual(high % 5, 0)
        self.assertLess(low, high)

    def test_scale_duration_high_never_equals_low(self):
        # high must always be greater than low
        for atype in ACTIVITY_DURATION_MULT:
            low, high = _scale_duration(atype, 30, 30)
            self.assertGreater(high, low, msg=f"Failed for activity type: {atype}")

    def test_unknown_activity_type_defaults_to_1x(self):
        # An unrecognized activity type defaults to 1.0 multiplier
        low, high = _scale_duration("Unknown", 60, 80)
        self.assertEqual(low, 60)
        self.assertEqual(high, 80)


#Tests for the forms

class DailyLogFormTest(TestCase):
    # Tests that DailyLogForm validates input correctly

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
    # Tests that ActivityForm validates RPE and required fields

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


#Tests for all the views and html templates

class AuthRedirectTest(TestCase):
    # Unauthenticated users should be redirected to login for all protected views

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
    # Logged-in users should get 200 OK on all main views

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


#Tests for the tmrws plan algo

class TomorrowPlanZoneTest(TestCase):
    # Tests the zone-selection logic of tomorrow_view by creating realistic
    # log data and checking what zone the view assigns in its context

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
        # Anchor day with < 2 hours sleep → REST zone
        self._create_log(days_ago=0, sleep_hours=1.5)
        self.assertEqual(self._get_zone(), "REST")

    def test_rest_day_triggered_by_very_high_rpe(self):
        # 120+ minutes at RPE 9+ on anchor day → REST zone
        self._create_log(
            days_ago=0,
            activities=[
                {"type": "Run", "name": "Long Hard Run", "duration": 130, "rpe": 9},
            ]
        )
        self.assertEqual(self._get_zone(), "REST")

    def test_recovery_zone_after_hard_effort(self):
        # Avg RPE >= 8 on anchor day → RECOVERY zone (no rest triggers)
        self._create_log(
            days_ago=0,
            sleep_hours=7,
            activities=[
                {"type": "Run", "name": "Hard Run", "duration": 50, "rpe": 8},
            ]
        )
        self.assertEqual(self._get_zone(), "RECOVERY")

    def test_easy_zone_from_bad_sleep(self):
        # 7-day avg sleep < 6 hours → EASY zone (no harder triggers)
        for i in range(7):
            self._create_log(days_ago=i, sleep_hours=5, sleep_quality=4, wellness=6, stress=4)
        self.assertEqual(self._get_zone(), "EASY")

    def test_hard_zone_conditions(self):
        # Good 7-day sleep (>7.5h, quality >7) + yesterday low RPE (<=4) → HARD zone
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
        # No logs at all → MODERATE (default fallback)
        self.assertEqual(self._get_zone(), "MODERATE")

    def test_three_suggestions_returned(self):
        # With activity history, tomorrow view returns exactly 3 suggestion cards
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
        # Creating two logs for the same date should fail
        self._create_log(days_ago=0)
        with self.assertRaises(Exception):
            self._create_log(days_ago=0)


# Tests for POST functionality in log and activity views

class LogCreatePostTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(username="postcreateuser", password="pass")
        self.client.login(username="postcreateuser", password="pass")

    def test_valid_post_creates_log_and_redirects(self):
        response = self.client.post(reverse("log_create"), {
            "date": str(date.today()),
            "sleep_hours": "7.5",
            "sleep_quality": "8",
            "wellness": "7",
            "stress": "3",
            "notes": "",
        })
        self.assertRedirects(response, reverse("logs"))
        self.assertTrue(DailyLog.objects.filter(user=self.user, date=date.today()).exists())

    def test_duplicate_date_post_shows_form_error(self):
        DailyLog.objects.create(user=self.user, date=date.today())
        response = self.client.post(reverse("log_create"), {
            "date": str(date.today()),
            "sleep_hours": "7",
            "sleep_quality": "7",
            "wellness": "7",
            "stress": "3",
            "notes": "",
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn("date", response.context["form"].errors)

    def test_invalid_post_stays_on_form(self):
        response = self.client.post(reverse("log_create"), {"date": "", "sleep_hours": "7"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(DailyLog.objects.filter(user=self.user).exists())


class LogDeleteTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(username="deleteuser", password="pass")
        self.other = User.objects.create_user(username="otheruserD", password="pass")
        self.client.login(username="deleteuser", password="pass")
        self.log = DailyLog.objects.create(user=self.user, date=date.today())

    def test_get_renders_confirmation_page(self):
        response = self.client.get(reverse("log_delete", args=[self.log.id]))
        self.assertEqual(response.status_code, 200)

    def test_post_deletes_log_and_redirects(self):
        response = self.client.post(reverse("log_delete", args=[self.log.id]))
        self.assertRedirects(response, reverse("logs"))
        self.assertFalse(DailyLog.objects.filter(id=self.log.id).exists())

    def test_cannot_delete_other_users_log(self):
        other_log = DailyLog.objects.create(user=self.other, date=date.today())
        response = self.client.post(reverse("log_delete", args=[other_log.id]))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(DailyLog.objects.filter(id=other_log.id).exists())


class ActivityAddTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(username="actadduser", password="pass")
        self.other = User.objects.create_user(username="otheruserA", password="pass")
        self.client.login(username="actadduser", password="pass")
        self.log = DailyLog.objects.create(user=self.user, date=date.today())
        self.other_log = DailyLog.objects.create(user=self.other, date=date.today())

    def test_get_renders_form(self):
        response = self.client.get(reverse("activity_add", args=[self.log.id]))
        self.assertEqual(response.status_code, 200)

    def test_valid_post_creates_activity_and_redirects(self):
        response = self.client.post(reverse("activity_add", args=[self.log.id]), {
            "name_of_activity": "Afternoon Run",
            "activity_type": "Run",
            "duration_min": "45",
            "rpe": "6",
            "distance": "5",
            "distance_unit": "Miles",
            "notes": "",
        })
        self.assertRedirects(response, reverse("logs"))
        self.assertEqual(self.log.activities.count(), 1)

    def test_invalid_post_stays_on_form(self):
        response = self.client.post(reverse("activity_add", args=[self.log.id]), {
            "activity_type": "",
            "duration_min": "45",
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.log.activities.count(), 0)

    def test_cannot_add_activity_to_other_users_log(self):
        response = self.client.get(reverse("activity_add", args=[self.other_log.id]))
        self.assertEqual(response.status_code, 404)


# Tests for model __str__ methods

class ModelStrTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(username="struser", password="pass")
        self.today = date.today()
        self.log = DailyLog.objects.create(user=self.user, date=self.today)

    def test_daily_log_str(self):
        self.assertEqual(str(self.log), f"struser - {self.today}")

    def test_activity_str(self):
        act = Activity.objects.create(
            daily_log=self.log, activity_type="Run", duration_min=45
        )
        self.assertEqual(str(act), f"Run (45 min) - {self.today}")


# Additional validator edge cases

class AdditionalValidatorTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(username="valuser2", password="pass")
        self.log = DailyLog.objects.create(user=self.user, date=date.today())

    def test_negative_rpe_is_invalid(self):
        act = Activity(daily_log=self.log, activity_type="Run", duration_min=30, rpe=Decimal("-1"))
        with self.assertRaises(ValidationError):
            act.full_clean()

    def test_negative_distance_is_invalid(self):
        act = Activity(daily_log=self.log, activity_type="Run", duration_min=30, distance=-1.0)
        with self.assertRaises(ValidationError):
            act.full_clean()


# Tests for tomorrow view context beyond zone selection

class TomorrowViewContextTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(username="tmrwctxuser", password="pass")
        self.client.login(username="tmrwctxuser", password="pass")
        self.today = date.today()

    def test_rest_zone_dur_low_and_high_are_none(self):
        DailyLog.objects.create(user=self.user, date=self.today, sleep_hours=Decimal("1.0"))
        response = self.client.get(reverse("tomorrow"))
        self.assertIsNone(response.context["dur_low"])
        self.assertIsNone(response.context["dur_high"])

    def test_rest_zone_suggestions_are_walk_stretch_yoga(self):
        DailyLog.objects.create(user=self.user, date=self.today, sleep_hours=Decimal("1.0"))
        response = self.client.get(reverse("tomorrow"))
        names = [s["name"] for s in response.context["suggestions"]]
        self.assertEqual(names, ["Walk", "Stretch", "Yoga"])

    def test_has_today_log_true_when_todays_log_exists(self):
        DailyLog.objects.create(user=self.user, date=self.today)
        response = self.client.get(reverse("tomorrow"))
        self.assertTrue(response.context["has_today_log"])

    def test_has_today_log_false_when_no_todays_log(self):
        response = self.client.get(reverse("tomorrow"))
        self.assertFalse(response.context["has_today_log"])

    def test_no_activity_history_returns_one_generic_suggestion(self):
        # Log exists but no activities → falls back to a single generic suggestion card
        DailyLog.objects.create(
            user=self.user, date=self.today,
            sleep_hours=Decimal("8"), sleep_quality=Decimal("8"),
            wellness=Decimal("8"), stress=Decimal("2"),
        )
        response = self.client.get(reverse("tomorrow"))
        self.assertEqual(len(response.context["suggestions"]), 1)


# Tests for history view context values

class HistoryViewContextTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(username="histuser", password="pass")
        self.client.login(username="histuser", password="pass")
        self.today = date.today()

    def test_total_count_matches_number_of_activities(self):
        log = DailyLog.objects.create(user=self.user, date=self.today)
        Activity.objects.create(daily_log=log, activity_type="Run", duration_min=30)
        Activity.objects.create(daily_log=log, activity_type="Bike", duration_min=45)
        response = self.client.get(reverse("history"))
        self.assertEqual(response.context["total_count"], 2)

    def test_first_and_last_date_are_populated(self):
        old_date = self.today - timedelta(days=5)
        log_old = DailyLog.objects.create(user=self.user, date=old_date)
        log_new = DailyLog.objects.create(user=self.user, date=self.today)
        Activity.objects.create(daily_log=log_old, activity_type="Walk", duration_min=20)
        Activity.objects.create(daily_log=log_new, activity_type="Run", duration_min=40)
        response = self.client.get(reverse("history"))
        self.assertEqual(response.context["first_date"], old_date)
        self.assertEqual(response.context["last_date"], self.today)

    def test_empty_history_has_none_for_dates(self):
        response = self.client.get(reverse("history"))
        self.assertIsNone(response.context["first_date"])
        self.assertIsNone(response.context["last_date"])


# Tests for history view filtering

class HistoryFilterTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(username="histfilteruser", password="pass")
        self.client.login(username="histfilteruser", password="pass")
        self.today = date.today()
        log_today = DailyLog.objects.create(user=self.user, date=self.today)
        log_old = DailyLog.objects.create(user=self.user, date=self.today - timedelta(days=60))
        Activity.objects.create(daily_log=log_today, activity_type="Run", duration_min=30)
        Activity.objects.create(daily_log=log_today, activity_type="Bike", duration_min=45)
        Activity.objects.create(daily_log=log_old, activity_type="Run", duration_min=40)

    def test_type_filter_returns_only_matching_type(self):
        response = self.client.get(reverse("history") + "?type=Bike")
        self.assertEqual(response.context["total_count"], 1)

    def test_period_filter_excludes_old_activities(self):
        response = self.client.get(reverse("history") + "?period=30")
        self.assertEqual(response.context["total_count"], 2)

    def test_combined_type_and_period_filter(self):
        response = self.client.get(reverse("history") + "?type=Run&period=30")
        self.assertEqual(response.context["total_count"], 1)

    def test_invalid_period_falls_back_to_all(self):
        response = self.client.get(reverse("history") + "?period=notanumber")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total_count"], 3)

    def test_selected_type_and_period_passed_to_context(self):
        response = self.client.get(reverse("history") + "?type=Run&period=7")
        self.assertEqual(response.context["selected_type"], "Run")
        self.assertEqual(response.context["selected_period"], "7")

    def test_unmatched_filter_returns_zero_count(self):
        response = self.client.get(reverse("history") + "?type=Swim")
        self.assertEqual(response.context["total_count"], 0)


# Tests for history view personal bests

class HistoryPersonalBestsTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(username="bestsuser", password="pass")
        self.client.login(username="bestsuser", password="pass")
        self.today = date.today()
        log = DailyLog.objects.create(user=self.user, date=self.today)
        Activity.objects.create(
            daily_log=log, activity_type="Run", duration_min=90,
            rpe=Decimal("8"), distance=10.0, distance_unit="Miles",
            post_workout_feeling=5,
        )
        Activity.objects.create(
            daily_log=log, activity_type="Bike", duration_min=45,
            rpe=Decimal("6"),
        )

    def test_best_duration_is_longest_activity(self):
        response = self.client.get(reverse("history"))
        self.assertEqual(response.context["best_duration"].duration_min, 90)

    def test_best_distance_is_farthest_activity(self):
        response = self.client.get(reverse("history"))
        self.assertEqual(response.context["best_distance"].distance, 10.0)

    def test_best_rpe_is_highest_effort(self):
        response = self.client.get(reverse("history"))
        self.assertEqual(float(response.context["best_rpe"].rpe), 8.0)

    def test_best_feeling_is_highest_rating(self):
        response = self.client.get(reverse("history"))
        self.assertEqual(response.context["best_feeling"].post_workout_feeling, 5)

    def test_best_distance_none_when_no_distance_logged(self):
        user2 = User.objects.create_user(username="nodistuser", password="pass")
        self.client.login(username="nodistuser", password="pass")
        log2 = DailyLog.objects.create(user=user2, date=self.today)
        Activity.objects.create(daily_log=log2, activity_type="Lift", duration_min=60)
        response = self.client.get(reverse("history"))
        self.assertIsNone(response.context["best_distance"])

    def test_personal_bests_unaffected_by_type_filter(self):
        # Filter to Bike (45 min) but best_duration should still be 90 (all-time)
        response = self.client.get(reverse("history") + "?type=Bike")
        self.assertEqual(response.context["best_duration"].duration_min, 90)


# Tests for post_workout_feeling field

class PostWorkoutFeelingTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(username="feelinguser", password="pass")
        self.log = DailyLog.objects.create(user=self.user, date=date.today())

    def test_valid_feeling_values_1_to_5_accepted(self):
        for val in range(1, 6):
            act = Activity(daily_log=self.log, activity_type="Run", duration_min=30,
                           name_of_activity="Morning Run", post_workout_feeling=val)
            try:
                act.full_clean()
            except ValidationError:
                self.fail(f"post_workout_feeling={val} should be valid")

    def test_feeling_above_5_is_invalid(self):
        act = Activity(daily_log=self.log, activity_type="Run", duration_min=30,
                       name_of_activity="Morning Run", post_workout_feeling=6)
        with self.assertRaises(ValidationError):
            act.full_clean()

    def test_feeling_below_1_is_invalid(self):
        act = Activity(daily_log=self.log, activity_type="Run", duration_min=30,
                       name_of_activity="Morning Run", post_workout_feeling=0)
        with self.assertRaises(ValidationError):
            act.full_clean()

    def test_feeling_is_optional(self):
        act = Activity(daily_log=self.log, activity_type="Run", duration_min=30,
                       name_of_activity="Morning Run")
        try:
            act.full_clean()
        except ValidationError:
            self.fail("post_workout_feeling should be optional")

    def test_feeling_display_labels(self):
        labels = {1: "Exhausted", 2: "Tired", 3: "Okay", 4: "Good", 5: "Great"}
        for val, expected in labels.items():
            act = Activity.objects.create(
                daily_log=self.log, activity_type="Run", duration_min=30,
                post_workout_feeling=val,
            )
            self.assertEqual(act.get_post_workout_feeling_display(), expected)
            act.delete()


# Tests for composite RPE (feeling adjusts zone selection)

class CompositeRpeZoneTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(username="comprpeuser", password="pass")
        self.client.login(username="comprpeuser", password="pass")
        self.today = date.today()

    def test_bad_feeling_after_moderate_rpe_triggers_recovery(self):
        # RPE 7 + feeling=1 (Exhausted, adj=+2) → composite 9 ≥ 8 → RECOVERY
        log = DailyLog.objects.create(user=self.user, date=self.today,
                                      sleep_hours=Decimal("7"))
        Activity.objects.create(
            daily_log=log, activity_type="Run", name_of_activity="Run",
            duration_min=45, rpe=Decimal("7"), post_workout_feeling=1,
        )
        response = self.client.get(reverse("tomorrow"))
        self.assertEqual(response.context["zone"], "RECOVERY")

    def test_great_feeling_after_hard_rpe_avoids_recovery(self):
        # RPE 8 + feeling=5 (Great, adj=-2) → composite 6 < 8 → not RECOVERY
        log = DailyLog.objects.create(user=self.user, date=self.today,
                                      sleep_hours=Decimal("7"))
        Activity.objects.create(
            daily_log=log, activity_type="Run", name_of_activity="Run",
            duration_min=45, rpe=Decimal("8"), post_workout_feeling=5,
        )
        zone = self.client.get(reverse("tomorrow")).context["zone"]
        self.assertNotEqual(zone, "RECOVERY")

    def test_reason_always_present_in_context(self):
        response = self.client.get(reverse("tomorrow"))
        self.assertIn("reason", response.context)
        self.assertIsInstance(response.context["reason"], str)
        self.assertGreater(len(response.context["reason"]), 0)


# Tests for DailyLog.grand_total and workout_recommendation

class GrandTotalTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(username="gtuser", password="pass")
        self.today = date.today()

    def _make_log(self, sleep_hours, sleep_quality, wellness, stress):
        return DailyLog(
            user=self.user, date=self.today,
            sleep_hours=sleep_hours, sleep_quality=sleep_quality,
            wellness=wellness, stress=stress,
        )

    def test_grand_total_perfect_recovery(self):
        # sleep_score=100 → 100/5=20, wellness=10, stress=0 → total=30
        log = self._make_log(9, 10, 10, 0)
        self.assertAlmostEqual(log.grand_total, 30.0, places=1)

    def test_grand_total_no_sleep_data(self):
        # sleep_score=None → 0/5=0, wellness=2, stress=8 → total=-6
        log = self._make_log(None, None, 2, 8)
        self.assertAlmostEqual(log.grand_total, -6.0, places=1)

    def test_workout_recommendation_rest_day(self):
        log = self._make_log(None, None, 2, 8)  # grand_total = -6 ≤ 5
        self.assertEqual(log.workout_recommendation, "Take a rest day or very light activity.")

    def test_workout_recommendation_hard_workout_ok(self):
        log = self._make_log(9, 10, 10, 0)  # grand_total = 30 > 25
        self.assertEqual(log.workout_recommendation, "You are recovered. Hard workout is okay.")


# Tests for log edit, activity edit, and activity delete views

class LogEditTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(username="logedituser", password="pass")
        self.other = User.objects.create_user(username="logeditother", password="pass")
        self.log = DailyLog.objects.create(user=self.user, date=date.today(), sleep_hours=7)
        self.client.login(username="logedituser", password="pass")
        self.url = reverse("log_edit", args=[self.log.id])

    def test_get_renders_form_with_existing_values(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Edit Log")
        self.assertEqual(response.context["form"].instance, self.log)

    def test_valid_post_saves_and_redirects(self):
        new_date = date.today() - timedelta(days=1)
        response = self.client.post(self.url, {
            "date": new_date.isoformat(),
            "sleep_hours": "8",
            "sleep_quality": "9",
            "wellness": "8",
            "stress": "2",
            "notes": "updated",
        })
        self.assertRedirects(response, reverse("logs"), fetch_redirect_response=False)
        self.log.refresh_from_db()
        self.assertEqual(self.log.sleep_hours, 8)

    def test_cannot_edit_other_users_log(self):
        self.client.login(username="logeditother", password="pass")
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 404)

    def test_login_required(self):
        self.client.logout()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)


class ActivityEditTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(username="actedituser", password="pass")
        self.other = User.objects.create_user(username="acteditother", password="pass")
        self.log = DailyLog.objects.create(user=self.user, date=date.today())
        self.activity = Activity.objects.create(
            daily_log=self.log, activity_type="Run",
            name_of_activity="Morning Run", duration_min=30, rpe=6,
        )
        self.client.login(username="actedituser", password="pass")
        self.url = reverse("activity_edit", args=[self.activity.id])

    def test_get_renders_form_with_existing_values(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Edit Activity")
        self.assertEqual(response.context["form"].instance, self.activity)

    def test_valid_post_updates_activity_and_redirects(self):
        response = self.client.post(self.url, {
            "name_of_activity": "Evening Run",
            "activity_type": "Run",
            "duration_min": "45",
            "rpe": "7",
            "distance_unit": "Miles",
        })
        self.assertRedirects(response, reverse("logs"), fetch_redirect_response=False)
        self.activity.refresh_from_db()
        self.assertEqual(self.activity.name_of_activity, "Evening Run")
        self.assertEqual(self.activity.duration_min, 45)

    def test_invalid_post_stays_on_form(self):
        response = self.client.post(self.url, {
            "name_of_activity": "Run",
            "activity_type": "",  # missing required field
            "duration_min": "30",
            "distance_unit": "Miles",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Edit Activity")

    def test_cannot_edit_other_users_activity(self):
        self.client.login(username="acteditother", password="pass")
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 404)

    def test_login_required(self):
        self.client.logout()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)


class ActivityDeleteTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(username="actdeluser", password="pass")
        self.other = User.objects.create_user(username="actdelother", password="pass")
        self.log = DailyLog.objects.create(user=self.user, date=date.today())
        self.activity = Activity.objects.create(
            daily_log=self.log, activity_type="Run",
            name_of_activity="Morning Run", duration_min=30,
        )
        self.client.login(username="actdeluser", password="pass")
        self.url = reverse("activity_delete", args=[self.activity.id])

    def test_get_renders_confirm_page(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Delete Activity")
        self.assertContains(response, "Morning Run")

    def test_post_deletes_activity_and_redirects(self):
        response = self.client.post(self.url)
        self.assertRedirects(response, reverse("logs"), fetch_redirect_response=False)
        self.assertFalse(Activity.objects.filter(id=self.activity.id).exists())

    def test_cannot_delete_other_users_activity(self):
        self.client.login(username="actdelother", password="pass")
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 404)
        self.assertTrue(Activity.objects.filter(id=self.activity.id).exists())

    def test_login_required(self):
        self.client.logout()
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Activity.objects.filter(id=self.activity.id).exists())
