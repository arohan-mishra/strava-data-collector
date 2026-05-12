import csv
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

import requests
from dotenv import load_dotenv
from flask import Flask, redirect, render_template, request, session, url_for, send_file, abort

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", secrets.token_hex(32))

STRAVA_CLIENT_ID = os.getenv("STRAVA_CLIENT_ID")
STRAVA_CLIENT_SECRET = os.getenv("STRAVA_CLIENT_SECRET")
STRAVA_REDIRECT_URI = os.getenv("STRAVA_REDIRECT_URI", "http://localhost:5001/callback")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "change-me")

DATA_DIR = Path(os.getenv("DATA_DIR", "data"))
DATA_DIR.mkdir(exist_ok=True)
RUNS_CSV = DATA_DIR / "strava_runs_collected.csv"
ATHLETES_CSV = DATA_DIR / "athletes_collected.csv"

STRAVA_AUTH_URL = "https://www.strava.com/oauth/authorize"
STRAVA_TOKEN_URL = "https://www.strava.com/oauth/token"
STRAVA_ACTIVITIES_URL = "https://www.strava.com/api/v3/athlete/activities"

RUN_FIELDS = [
    "participant_id",
    "athlete_id",
    "activity_id",
    "name",
    "sport_type",
    "type",
    "distance_m",
    "moving_time_sec",
    "elapsed_time_sec",
    "total_elevation_gain_m",
    "start_date",
    "timezone",
    "average_speed_mps",
    "max_speed_mps",
    "average_heartrate",
    "max_heartrate",
    "has_heartrate",
    "average_cadence",
    "suffer_score",
    "trainer",
    "commute",
    "manual",
    "private",
    "visibility",
    "collected_at",
]

ATHLETE_FIELDS = [
    "participant_id",
    "athlete_id",
    "firstname",
    "lastname",
    "city",
    "state",
    "country",
    "sex",
    "created_at",
    "collected_at",
]


def append_rows(csv_path: Path, fieldnames: list[str], rows: list[dict]):
    file_exists = csv_path.exists()
    with csv_path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def get_required_config():
    missing = []
    if not STRAVA_CLIENT_ID:
        missing.append("STRAVA_CLIENT_ID")
    if not STRAVA_CLIENT_SECRET:
        missing.append("STRAVA_CLIENT_SECRET")
    return missing


@app.route("/")
def index():
    missing = get_required_config()
    return render_template("index.html", missing=missing)


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


@app.route("/connect")
def connect():
    missing = get_required_config()
    if missing:
        return render_template("config_error.html", missing=missing), 500

    state = secrets.token_urlsafe(24)
    session["oauth_state"] = state

    params = {
        "client_id": STRAVA_CLIENT_ID,
        "redirect_uri": STRAVA_REDIRECT_URI,
        "response_type": "code",
        "approval_prompt": "auto",
        "scope": "read,activity:read_all",
        "state": state,
    }
    return redirect(f"{STRAVA_AUTH_URL}?{urlencode(params)}")


@app.route("/callback")
def callback():
    error = request.args.get("error")
    if error:
        return render_template("error.html", message=f"Strava returned an error: {error}"), 400

    code = request.args.get("code")
    state = request.args.get("state")
    expected_state = session.pop("oauth_state", None)

    if not code:
        return render_template("error.html", message="Missing OAuth authorization code."), 400
    if not expected_state or state != expected_state:
        return render_template("error.html", message="Invalid OAuth state. Please try again."), 400

    token_response = requests.post(
        STRAVA_TOKEN_URL,
        data={
            "client_id": STRAVA_CLIENT_ID,
            "client_secret": STRAVA_CLIENT_SECRET,
            "code": code,
            "grant_type": "authorization_code",
        },
        timeout=30,
    )

    print(token_response.status_code)
    print(token_response.text)

    if token_response.status_code != 200:
        return render_template(
            "error.html",
            message=f"Could not exchange code for token. Status: {token_response.status_code}. Response: {token_response.text}",
        ), 400

    token_data = token_response.json()
    access_token = token_data.get("access_token")
    athlete = token_data.get("athlete", {})

    if not access_token:
        return render_template("error.html", message="No access token returned by Strava."), 400

    participant_id = secrets.token_hex(8)
    collected_at = datetime.now(timezone.utc).isoformat()
    athlete_id = athlete.get("id", "")

    athlete_row = {
        "participant_id": participant_id,
        "athlete_id": athlete_id,
        "firstname": athlete.get("firstname", ""),
        "lastname": athlete.get("lastname", ""),
        "city": athlete.get("city", ""),
        "state": athlete.get("state", ""),
        "country": athlete.get("country", ""),
        "sex": athlete.get("sex", ""),
        "created_at": athlete.get("created_at", ""),
        "collected_at": collected_at,
    }
    append_rows(ATHLETES_CSV, ATHLETE_FIELDS, [athlete_row])

    run_rows = fetch_run_activities(access_token, participant_id, athlete_id, collected_at)
    if run_rows:
        append_rows(RUNS_CSV, RUN_FIELDS, run_rows)

    return render_template("success.html", run_count=len(run_rows), participant_id=participant_id)


def fetch_run_activities(access_token: str, participant_id: str, athlete_id: str, collected_at: str) -> list[dict]:
    headers = {"Authorization": f"Bearer {access_token}"}
    all_runs = []
    page = 1

    while True:
        params = {"per_page": 200, "page": page}
        response = requests.get(STRAVA_ACTIVITIES_URL, headers=headers, params=params, timeout=30)

        if response.status_code != 200:
            raise RuntimeError(f"Strava activities request failed: {response.status_code} {response.text}")

        activities = response.json()
        if not activities:
            break

        for activity in activities:
            activity_type = activity.get("type")
            sport_type = activity.get("sport_type")
            if activity_type == "Run" or sport_type in {"Run", "TrailRun", "VirtualRun"}:
                all_runs.append({
                    "participant_id": participant_id,
                    "athlete_id": athlete_id,
                    "activity_id": activity.get("id"),
                    "name": activity.get("name"),
                    "sport_type": sport_type,
                    "type": activity_type,
                    "distance_m": activity.get("distance"),
                    "moving_time_sec": activity.get("moving_time"),
                    "elapsed_time_sec": activity.get("elapsed_time"),
                    "total_elevation_gain_m": activity.get("total_elevation_gain"),
                    "start_date": activity.get("start_date"),
                    "timezone": activity.get("timezone"),
                    "average_speed_mps": activity.get("average_speed"),
                    "max_speed_mps": activity.get("max_speed"),
                    "average_heartrate": activity.get("average_heartrate"),
                    "max_heartrate": activity.get("max_heartrate"),
                    "has_heartrate": activity.get("has_heartrate"),
                    "average_cadence": activity.get("average_cadence"),
                    "suffer_score": activity.get("suffer_score"),
                    "trainer": activity.get("trainer"),
                    "commute": activity.get("commute"),
                    "manual": activity.get("manual"),
                    "private": activity.get("private"),
                    "visibility": activity.get("visibility"),
                    "collected_at": collected_at,
                })

        page += 1

    return all_runs


@app.route("/admin")
def admin():
    return render_template("admin.html")


@app.route("/download/runs")
def download_runs():
    password = request.args.get("password")
    if password != ADMIN_PASSWORD:
        abort(403)
    if not RUNS_CSV.exists():
        return render_template("error.html", message="No running activity data has been collected yet."), 404
    return send_file(RUNS_CSV, as_attachment=True, download_name="strava_runs_collected.csv")


@app.route("/download/athletes")
def download_athletes():
    password = request.args.get("password")
    if password != ADMIN_PASSWORD:
        abort(403)
    if not ATHLETES_CSV.exists():
        return render_template("error.html", message="No athlete data has been collected yet."), 404
    return send_file(ATHLETES_CSV, as_attachment=True, download_name="athletes_collected.csv")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5001)), debug=os.getenv("FLASK_DEBUG", "0") == "1")
