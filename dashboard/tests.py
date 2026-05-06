from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from dashboard.views import _nice_max, _svg_points, _y_ticks
from workouts.models import Activity, DailyLog


class NiceMaxTest(TestCase):

    def test_zero_or_negative_returns_one(self):
        self.assertEqual(_nice_max(0), 1)

    def test_value_exactly_at_option(self):
        self.assertEqual(_nice_max(10), 10)

    def test_value_just_over_option_rounds_up(self):
        # 11 is above 10, next nice option is 12
        self.assertEqual(_nice_max(11), 12)

    def test_large_value_rounds_to_50_multiples(self):
        # 151 exceeds all preset options → ceil(151/50)*50 = 200
        self.assertEqual(_nice_max(151), 200)

    def test_small_value_returns_first_option(self):
        self.assertEqual(_nice_max(1), 1)


class YTicksTest(TestCase):

    def test_returns_num_ticks_plus_one_entries(self):
        ticks = _y_ticks(max_val=10, num_ticks=4)
        self.assertEqual(len(ticks), 5)

    def test_top_tick_y_equals_pad_top(self):
        ticks = _y_ticks(max_val=10, num_ticks=4, chart_height=120, pad_top=10, pad_bottom=28)
        max_tick = [t for t in ticks if t["label"] == 10]
        self.assertEqual(len(max_tick), 1)
        self.assertAlmostEqual(max_tick[0]["y"], 10.0)

    def test_integer_labels_for_large_max(self):
        ticks = _y_ticks(max_val=100, num_ticks=4)
        for tick in ticks:
            self.assertIsInstance(tick["label"], int)


class SvgPointsTest(TestCase):

    def test_returns_correct_number_of_coordinate_pairs(self):
        data = [{"value": 5}, {"value": 10}, {"value": 3}]
        points = _svg_points(data, "value")
        self.assertEqual(len(points.split(" ")), 3)

    def test_first_point_x_equals_pad_left(self):
        data = [{"value": 5}, {"value": 10}]
        _svg_points(data, "value", pad_left=24)
        self.assertEqual(data[0]["x"], 24)

    def test_single_item_does_not_crash(self):
        data = [{"value": 7}]
        points = _svg_points(data, "value")
        self.assertIsNotNone(points)


class TrainingLoadZoneTest(TestCase):
    # Tests that training_load_view returns the correct zone label.
    # avg_daily_load = sum(duration * rpe across 7-day activities) / 7

    def setUp(self):
        self.user = User.objects.create_user(username="loaduser", password="pass")
        self.client.login(username="loaduser", password="pass")
        self.today = date.today()

    def _make_activity(self, duration, rpe, days_ago=0):
        log_date = self.today - timedelta(days=days_ago)
        log, _ = DailyLog.objects.get_or_create(user=self.user, date=log_date)
        Activity.objects.create(
            daily_log=log, activity_type="Run",
            duration_min=duration, rpe=Decimal(str(rpe)),
        )

    def test_low_zone_label(self):
        # 30 min * RPE 5 = 150 total → avg = 150/7 ≈ 21 → "Low" (< 300)
        self._make_activity(30, 5)
        response = self.client.get(reverse("training_load"))
        self.assertEqual(response.context["zone_label"], "Low")

    def test_moderate_zone_label(self):
        # 7 activities * 50 min * RPE 7 = 2450 total → avg = 350 → "Moderate" [300, 600)
        for i in range(7):
            self._make_activity(50, 7, days_ago=i)
        response = self.client.get(reverse("training_load"))
        self.assertEqual(response.context["zone_label"], "Moderate")

    def test_high_zone_label(self):
        # 7 activities * 90 min * RPE 7 = 4410 total → avg = 630 → "High" [600, 900)
        for i in range(7):
            self._make_activity(90, 7, days_ago=i)
        response = self.client.get(reverse("training_load"))
        self.assertEqual(response.context["zone_label"], "High")

    def test_overreaching_zone_label(self):
        # 7 activities * 130 min * RPE 10 = 9100 total → avg = 1300 → "Overreaching" (≥ 900)
        for i in range(7):
            self._make_activity(130, 10, days_ago=i)
        response = self.client.get(reverse("training_load"))
        self.assertEqual(response.context["zone_label"], "Overreaching")


class DashboardContextTest(TestCase):
    # Verifies the main dashboard view passes all expected context keys

    def setUp(self):
        self.user = User.objects.create_user(username="dashctxuser", password="pass")
        self.client.login(username="dashctxuser", password="pass")

    def test_all_expected_context_keys_present(self):
        response = self.client.get(reverse("dashboard"))
        expected_keys = [
            "today", "seven_days_ago", "total_hours", "mins", "act_count",
            "chart_data", "training_load", "load_percent", "avg_wellness",
            "avg_stress", "wellness_chart_data", "sleep_score", "gauge_degrees",
            "sleep_chart_data", "sleep_line_points",
        ]
        for key in expected_keys:
            self.assertIn(key, response.context, msg=f"Missing context key: '{key}'")

    def test_chart_data_covers_seven_days(self):
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(len(response.context["chart_data"]), 7)

    def test_wellness_chart_data_covers_seven_days(self):
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(len(response.context["wellness_chart_data"]), 7)
