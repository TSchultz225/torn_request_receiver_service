# Pulse Discord Relay

A small FastAPI service that accepts a POST request from your client script and forwards a controlled embed to a private Discord webhook.

## Endpoints

- `GET /` - service info
- `GET /health` - health check
- `POST /send` - main relay endpoint
- `POST /v1/send` - alias for `/send`

## Local run

1. Update `.env` - Fill in `DISCORD_WEBHOOK_URL`
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Start the server:
   ```bash
   uvicorn server:app --host 0.0.0.0 --port 8000
   ```

## Example request body

```json
{
  "script_version": "0.8.9",
  "title": "🚑 Pulse Revive Request",
  "user_name": "ExampleUser",
  "user_id": "123456",
  "faction_name": "Example Faction",
  "is_hospitalized": true,
  "hospital_time": "15.0 minutes",
  "hospital_reason": "Mugged by Someone",
  "location": "Torn City",
  "profile_url": "https://www.torn.com/profiles.php?XID=123456",
  "timestamp": "2026-03-11T20:00:00.000Z"
}
```

## Notes

- The built-in rate limiter is in-memory. For multiple instances, Redis would be a good option