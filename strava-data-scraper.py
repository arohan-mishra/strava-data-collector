import requests
import pandas as pd

ACCESS_TOKEN = "b70391081cf81f1dd995722eb3e41d8395eacb8d"

url = "https://www.strava.com/api/v3/athlete/activities"

headers = {
    "Authorization": f"Bearer {ACCESS_TOKEN}"
}

params = {
    "per_page": 200,
    "page": 1
}

# -----------------------------
# Get all activities
# -----------------------------
 
 
all_activities = []

while True:
    response = requests.get(url, headers=headers, params=params)

    if response.status_code != 200:
        print("Error:", response.status_code)
        print(response.text)
        break

    data = response.json()

    if not isinstance(data, list) or len(data) == 0:
        break

    # Store full activity JSON
    all_activities.extend(data)

    params["page"] += 1

# -----------------------------
# Convert to DataFrame
# -----------------------------
df = pd.json_normalize(all_activities)

# -----------------------------
# Save raw dataset
# -----------------------------
df.to_csv("strava_all_activities_raw.csv", index=False)

print(f"Saved {len(df)} activities to CSV")


# -----------------------------
# Filter for running activities and select relevant columns
# -----------------------------
filtered_runs = []

for activity in all_activities:
    if activity.get("type") == "Run":
        filtered_runs.append({
            "name": activity.get("name"),
            "distance": activity.get("distance"),
            "moving_time": activity.get("moving_time"),
            "elapsed_time": activity.get("elapsed_time"),
            "total_elevation_gain": activity.get("total_elevation_gain"),
            "start_date": activity.get("start_date"),
            "location_city": activity.get("location_city"),
            "start_latlng": activity.get("start_latlng"),
            "end_latlng": activity.get("end_latlng"),
            "average_speed": activity.get("average_speed"),
            "max_speed": activity.get("max_speed"),
            "has_heartrate": activity.get("has_heartrate"),
            "heartrate_opt_out": activity.get("heartrate_opt_out"),
            "suffer_score": activity.get("suffer_score"),
            "average_cadence": activity.get("average_cadence"),
            "average_heartrate": activity.get("average_heartrate"),
            "max_heartrate": activity.get("max_heartrate")
        })

# Convert to DataFrame
df_runs = pd.DataFrame(filtered_runs)

# Save filtered dataset
df_runs.to_csv("strava_runs_filtered.csv", index=False)

print(f"Saved {len(df_runs)} running activities")
