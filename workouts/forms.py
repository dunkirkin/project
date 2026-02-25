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
        fields = [
            'name_of_activity',
            'activity_type',
            'duration_min',
            'distance',
            'distance_unit',
            'rpe'
        ]
        widgets = {
            "name_of_activity": forms.TextInput(attrs={"class": "medium-input"}),
            "duration_min": forms.NumberInput(attrs={"class": "small-input"}),
            "distance": forms.NumberInput(attrs={"class": "small-input"}),
            "rpe": forms.NumberInput(attrs={"class": "small-input"}),
        }
