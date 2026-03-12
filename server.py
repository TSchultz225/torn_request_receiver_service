import os
import time
from collections import defaultdict, deque
from typing import Optional

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

load_dotenv()

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
PORT = int(os.getenv("PORT", "8000"))
RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60")) #default to 10
RATE_LIMIT_MAX_REQUESTS = int(os.getenv("RATE_LIMIT_MAX_REQUESTS", "10")) #default to 1
MAX_REASON_LENGTH = int(os.getenv("MAX_REASON_LENGTH", "300")) #default to 300
ALLOWED_LOCATIONS = {"Torn City", "Abroad"}
REQUEST_TIMEOUT_SECONDS = 10

if not DISCORD_WEBHOOK_URL:
    raise RuntimeError("Missing DISCORD_WEBHOOK_URL environment variable")

app = FastAPI(title="Pulse Discord Relay", version="1.0.0")

# In-memory rate limiter.
_request_log: dict[str, deque[float]] = defaultdict(deque)


class ReviveRequest(BaseModel):
    script_version: str = Field(..., min_length=1, max_length=20)
    title: str = Field(..., min_length=1, max_length=100)
    user_name: str = Field(..., min_length=1, max_length=100)
    user_id: str = Field(..., min_length=1, max_length=50)
    faction_name: str = Field(..., min_length=1, max_length=100)
    is_hospitalized: bool
    hospital_time: Optional[str] = Field(default=None, max_length=100)
    hospital_reason: Optional[str] = Field(default=None, max_length=MAX_REASON_LENGTH)
    location: str = Field(..., min_length=1, max_length=50)
    profile_url: str = Field(..., min_length=1, max_length=300)
    timestamp: str = Field(..., min_length=1, max_length=100)

    @field_validator("location")
    @classmethod
    def validate_location(cls, value: str) -> str:
        if value not in ALLOWED_LOCATIONS:
            raise ValueError("location must be 'Torn City' or 'Abroad'")
        return value

    @field_validator("profile_url")
    @classmethod
    def validate_profile_url(cls, value: str) -> str:
        if not value.startswith("https://www.torn.com/profiles.php?XID="):
            raise ValueError("profile_url must point to a Torn profile")
        return value


def get_client_ip(request: Request) -> str:
    # Prefer proxy headers when running behind Render/Railway.
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    if request.url.path not in {"/send", "/v1/send"}:
        return await call_next(request)

    ip = get_client_ip(request)
    now = time.time()
    bucket = _request_log[ip]

    while bucket and now - bucket[0] > RATE_LIMIT_WINDOW_SECONDS:
        bucket.popleft()

    if len(bucket) >= RATE_LIMIT_MAX_REQUESTS:
        return JSONResponse(
            status_code=429,
            content={
                "detail": (
                    f"Rate limit exceeded. Max {RATE_LIMIT_MAX_REQUESTS} requests per "
                    f"{RATE_LIMIT_WINDOW_SECONDS} seconds per IP."
                )
            },
        )

    bucket.append(now)
    return await call_next(request)


@app.get("/")
def root():
    return {
        "service": "pulse-discord-relay",
        "status": "ok",
        "version": app.version,
    }


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.post("/send")
@app.post("/v1/send")
def send_to_discord(data: ReviveRequest):
    hospital_status = (
        f"Time remaining: **{data.hospital_time or 'Unknown'}** {data.hospital_reason or ''}".strip()
        if data.is_hospitalized
        else "User is not hospitalized (Test Mode)"
    )

    discord_payload = {
        "embeds": [
            {
                "title": data.title,
                "color": 15158332 if data.is_hospitalized else 8421504,
                "fields": [
                    {
                        "name": "User",
                        "value": f"[{data.user_name} [{data.user_id}]]({data.profile_url})",
                        "inline": True,
                    },
                    {
                        "name": "Faction",
                        "value": data.faction_name,
                        "inline": True,
                    },
                    {
                        "name": "Hospital Status",
                        "value": hospital_status,
                        "inline": False,
                    },
                    {
                        "name": "Location",
                        "value": data.location,
                        "inline": False,
                    },
                ],
                "footer": {"text": f"Pulse Revive System v{data.script_version}"},
                "timestamp": data.timestamp,
            }
        ]
    }

    try:
        response = requests.post(
            DISCORD_WEBHOOK_URL,
            json=discord_payload,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"Failed to reach Discord: {exc}") from exc

    if response.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail=f"Discord webhook failed: {response.status_code} {response.text}",
        )

    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("server:app", host="0.0.0.0", port=PORT, reload=False)
