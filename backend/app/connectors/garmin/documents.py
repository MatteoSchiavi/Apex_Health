"""Additional documented Garmin API read surfaces, retained without guessing units.

These responses are source documents, not synthetic canonical measurements.
The date range forms use a single day, within each documented range limit.
"""
DAILY_DOCUMENTS = {
    "hydration": ("/usersummary-service/stats/hydration/daily/{day}/{day}", None),
    "daily_steps": ("/usersummary-service/stats/steps/daily/{day}/{day}", None),
    "daily_stress": ("/usersummary-service/stats/stress/daily/{day}/{day}", None),
    "food_logs": ("/nutrition-service/food/logs/{day}", None),
    "body_battery": ("/wellness-service/wellness/bodyBattery/reports/daily", {"startDate": "{day}", "endDate": "{day}"}),
    "heart_rate": ("/wellness-service/wellness/dailyHeartRate", {"date": "{day}"}),
    "spo2": ("/wellness-service/wellness/daily/spo2acclimation/{day}", None),
    "fitness_age": ("/fitnessage-service/fitnessage/v2/{day}", None),
    "daily_summary_v2": ("/usersummary-service/v2/dailysummaries", {"startDate": "{day}", "endDate": "{day}"}),
    "wellness_activities": ("/wellnessactivity-service/activity/summary/range/{day}/{day}", None),
    "weight_goals": ("/goal-service/goal/user/effective/weightgoal/{day}/{day}", None),
    "cycle_summary": ("/periodichealth-service/menstrualcycle/summary/{day}", None),
    "cycle_day": ("/periodichealth-service/menstrualcycle/dayview/{day}", {"todayDate": "{today}"}),
}
PROFILE_DOCUMENTS = {
    "profile_settings": ("/userprofile-service/userprofile/settings", None),
    "heart_rate_zones": ("/biometric-service/heartRateZones/v2", None),
}
