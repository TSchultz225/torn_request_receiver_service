import os
from typing import Optional

import requests
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

if not DISCORD_WEBHOOK_URL:
    raise RuntimeError("Missing DISCORD_WEBHOOK_URL")


class DiscordMessage(BaseModel):
    content: Optional[str] = None
    username: Optional[str] = None


@app.post("/send")
def send_to_discord(
    payload: DiscordMessage,
    x_api_key: Optional[str] = Header(default=None)
):
    if x_api_key != INTERNAL_API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")

    if not payload.content:
        raise HTTPException(status_code=400, detail="Message content is required")

    discord_payload = {
        "content": payload.content
    }

    if payload.username:
        discord_payload["username"] = payload.username

    response = requests.post(DISCORD_WEBHOOK_URL, json=discord_payload, timeout=10)

    if response.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail=f"Discord returned {response.status_code}: {response.text}"
        )

    return {"status": "ok"}