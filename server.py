import logging
import os
import time
from collections import defaultdict, deque
from typing import Optional

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field, ValidationError

load_dotenv()


# Logging Setup
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

logger = logging.getLogger("pulse-relay")

app = FastAPI(title="Pulse Relay")

# Env Vars Setup
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))
RATE_LIMIT_MAX_REQUESTS = int(os.getenv("RATE_LIMIT_MAX_REQUESTS", "10"))

if not DISCORD_WEBHOOK_URL:
    logger.error("DISCORD_WEBHOOK_URL is missing")
    raise RuntimeError("Missing DISCORD_WEBHOOK_URL")

# Simple in-memory rate limiter
request_log = defaultdict(deque)


class ReviveRequest(BaseModel):
    script_version: str = Field(..., min_length=1, max_length=20)
    title: str = Field(..., min_length=1, max_length=100)
    user_name: str = Field(..., min_length=1, max_length=100)
    user_id: str = Field(..., min_length=1, max_length=50)
    faction_name: str = Field(..., min_length=1, max_length=100)
    is_hospitalized: bool
    hospital_time: Optional[str] = Field(default=None, max_length=100)
    hospital_reason: Optional[str] = Field(default=None, max_length=300)
    location: str = Field(..., min_length=1, max_length=50)
    profile_url: str = Field(..., min_length=1, max_length=300)
    timestamp: str = Field(..., min_length=1, max_length=100)


def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def check_rate_limit(ip: str) -> bool:
    now = time.time()
    timestamps = request_log[ip]

    while timestamps and now - timestamps[0] > RATE_LIMIT_WINDOW_SECONDS:
        timestamps.popleft()

    if len(timestamps) >= RATE_LIMIT_MAX_REQUESTS:
        return False

    timestamps.append(now)
    return True


@app.middleware("http")
async def log_requests(request: Request, call_next):
    ip = get_client_ip(request)
    logger.info("Incoming request: method=%s path=%s ip=%s", request.method, request.url.path, ip)

    try:
        response = await call_next(request)
        logger.info(
            "Completed request: method=%s path=%s ip=%s status=%s",
            request.method,
            request.url.path,
            ip,
            response.status_code,
        )
        return response
    except Exception:
        logger.exception("Unhandled server error for ip=%s path=%s", ip, request.url.path)
        raise


@app.get("/health")
def health():
    logger.info("Health check called")
    return {"status": "ok"}


@app.post("/send")
async def send_to_discord(request: Request):
    ip = get_client_ip(request)

    if not check_rate_limit(ip):
        logger.warning("Rate limit exceeded for ip=%s", ip)
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    # Read raw body first so we can log malformed JSON too
    try:
        raw_body = await request.body()
        raw_text = raw_body.decode("utf-8", errors="replace")
        logger.info("Raw request body from ip=%s: %s", ip, raw_text[:2000])
    except Exception:
        logger.exception("Failed reading raw request body from ip=%s", ip)
        raise HTTPException(status_code=400, detail="Could not read request body")

    # Parse JSON
    try:
        json_data = await request.json()
        logger.info("Parsed JSON from ip=%s successfully", ip)
    except Exception:
        logger.exception("Invalid JSON received from ip=%s", ip)
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # Validate payload
    try:
        data = ReviveRequest(**json_data)
        logger.info(
            "Validated payload from ip=%s user_id=%s user_name=%s hospitalized=%s",
            ip,
            data.user_id,
            data.user_name,
            data.is_hospitalized,
        )
    except ValidationError as e:
        logger.warning("Payload validation failed for ip=%s: %s", ip, e.json())
        raise HTTPException(status_code=422, detail=e.errors())

    hospital_status = (
        f"Time remaining: **{data.hospital_time}** {data.hospital_reason}"
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

    logger.info(
        "Forwarding request to Discord for user_id=%s script_version=%s",
        data.user_id,
        data.script_version,
    )
    logger.debug("Discord payload: %s", discord_payload)

    try:
        response = requests.post(
            DISCORD_WEBHOOK_URL,
            json=discord_payload,
            timeout=10,
        )

        logger.info(
            "Discord response for user_id=%s: status=%s body=%s",
            data.user_id,
            response.status_code,
            response.text[:2000],
        )

        if response.status_code >= 400:
            raise HTTPException(
                status_code=502,
                detail=f"Discord webhook failed: {response.status_code} {response.text}",
            )

    except requests.RequestException:
        logger.exception("Network error while sending to Discord for user_id=%s", data.user_id)
        raise HTTPException(status_code=502, detail="Network error while sending to Discord")

    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("server:app", host="0.0.0.0", port=PORT, reload=False)
