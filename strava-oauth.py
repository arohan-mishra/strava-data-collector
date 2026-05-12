import os
import requests
from dotenv import load_dotenv

load_dotenv()

client_id = os.getenv("STRAVA_CLIENT_ID")
client_secret = os.getenv("STRAVA_CLIENT_SECRET")
code = os.getenv("STRAVA_CODE")

response = requests.post(
    "https://www.strava.com/oauth/token",
    data={
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "grant_type": "authorization_code"
    }
)

print(response.json())
