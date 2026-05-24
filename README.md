# Saju Destiny — ជោគជតា

**Traditional Four Pillars of Destiny Fortune App for Cambodia**

Precise Saju analysis with AI-powered readings in Khmer and English.

## Features

- Four Pillars (Saju) chart calculation
- AI-powered fortune readings (Khmer + English)
- Monthly, daily, and compatibility analysis
- Life stage fortune overview
- Lucky colors, directions, and numbers
- User registration and history

## Tech Stack

- **Backend**: Python FastAPI + SQLite
- **Frontend**: Vanilla HTML/CSS/JavaScript (PWA)
- **AI**: OpenAI GPT (Khmer + English bilingual)

## Deployment

Deployed on Railway.app. Environment variables required:

| Variable | Description |
|----------|-------------|
| `OPENAI_API_KEY` | OpenAI API key |
| `OPENAI_BASE_URL` | OpenAI base URL |
| `AI_MODEL` | Model name (e.g., gpt-4.1-mini) |
| `APP_ENV` | production |
| `CORS_ORIGINS` | * or specific domains |

## Local Development

```bash
pip install -r requirements.txt
uvicorn main:app --reload --port 8001
```
