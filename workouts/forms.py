from django import forms
from .models import DailyLog, Activity

# form to allow user to log their exercise stats
class DailyLogForm(forms.ModelForm):
    class Meta:
        model = DailyLog
        fields = ["date", "sleep_hours", "sleep_quality", "wellness", "stress", "notes"]
# allows user to input their activites
class ActivityForm(forms.ModelForm):
    class Meta:
        model = Activity
        fields = ["activity_type", "duration_min", "rpe", "distance"]
