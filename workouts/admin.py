from django.contrib import admin

# Register your models here.
from .models import DailyLog, Activity

class ActivityInline(admin.TabularInline):
    model = Activity
    extra = 1
    #This is for when editing a daily log, show related Activity objects directly inside it


@admin.register(DailyLog)
class DailyLogAdmin(admin.ModelAdmin):
    inlines = [ActivityInline]
    list_display = ("user", "date", "sleep_hours", "wellness")


@admin.register(Activity)
class ActivityAdmin(admin.ModelAdmin):
    list_display = ("activity_type", "duration_min", "daily_log")