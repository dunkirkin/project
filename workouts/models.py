from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator

# Create your models here.
# This will represent one calendar day for a specfic user
#Stores recovery and wellness for entire day
#Sleep quality can be 1-10 scale
#wellness and stress can 1-10 scale
#Overall notes for day for history tab
class DailyLog(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="daily_logs")
    date = models.DateField()
    sleep_hours = models.DecimalField(max_digits=3, decimal_places=1, null=True, blank=True)
    # limiting the user input to 1-10 for sleep quality, wellness, and stress
    sleep_quality = models.PositiveSmallIntegerField(
        null=True, blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(10)]
    )
    wellness = models.PositiveSmallIntegerField(
        null=True, blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(10)]
    )
    stress = models.PositiveSmallIntegerField(
        null=True, blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(10)]
    )
    
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "date")
        ordering = ["-date"]
        #One daily log per date per user sorted in descending order by date

    def __str__(self):
        return f"{self.user.username} - {self.date}"
        #This will control how this object appears in admin
        #an example output would be jake - 2026-02-11
        
    # this is to total up the scores for sleep, wellness, and stress
    @property
    def recovery_score(self):
        sleep = self.sleep_quality or 0
        wellness = self.wellness or 0
        stress = self.stress or 0

        return sleep + wellness - stress
    
    # total up score for the rpe
    @property
    def activity_score(self):
        return sum((a.rpe or 0) for a in self.activities.all())
    
    #total up the recovery and activity
    @property
    def grand_total(self):
        return self.recovery_score + self.activity_score
    
    @property
    def workout_recommendation(self):
        score = self.grand_total

        if score <= 5:
            return "Take a rest day or very light activity."
        elif score <= 15:
            return "Light workout recommended."
        elif score <= 25:
            return "Moderate workout recommended."
        else:
            return "You are recovered. Hard workout is okay."
    
#This represents one single workout session
#Wanted to seperate this and daily log so people can put in 
# #Mulitple activites per day
class Activity(models.Model):

    name_of_activity = models.CharField(max_length=50, default="")

    ACTIVITY_CHOICES = [
        ("Run", "Run"),
        ("Walk", "Walk"),
        ("Hike", "Hike"),
        ("Bike", "Bike"),
        ("Moutain Bike", "Mountain Bike"),
        ("Yoga", "Yoga"),
        ("Sport", "Sport"),
        ("Lift", "Lift"),
        ("Swim", "Swim"),
        ("Other", "Other")
    ]

    DISTANCE_UNITS = [
        ("Miles", "mi"),
        ("Kilometers", "km"),
        ("Meters", "m"),
        ("Yards", "yd")
    ]
    daily_log = models.ForeignKey(DailyLog, on_delete=models.CASCADE, related_name="activities")
    #This line makes it so each activity belongs to one daily log
    activity_type = models.CharField(max_length=20, choices=ACTIVITY_CHOICES)
    duration_min = models.PositiveIntegerField(default=0)
    # limiting user input to 1-10 for rpe too
    rpe = models.PositiveSmallIntegerField(
        null=True, blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(10)]
    ) #rpe= Rate of Perceived Exertion so how hard they think it was
    distance = models.FloatField(null=True, blank=True)
    distance_unit = models.CharField(max_length=10, choices=DISTANCE_UNITS, default="Miles", null=True, blank=True)
    
    notes = models.TextField(blank=True) # user can make notes for themselves for each workout

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.activity_type} ({self.duration_min} min) - {self.daily_log.date}"
        #Will be stored in admin 
        #Example output would be 
        #Run (45 min) - 2026-02-11
