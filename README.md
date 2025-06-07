# Pesto Codex Slack Bot

This repository contains an example Slack bot that asks users two questions via a modal and stores their responses in Airtable.

## Prerequisites

- Python 3.8+
- A Slack app with bot token and signing secret
- An Airtable base with a table containing a `Handle` column (email or Slack handle)

Install dependencies:

```bash
pip install slack-bolt slack-sdk pyairtable
```

Set these environment variables before running the bot:

- `SLACK_BOT_TOKEN`
- `SLACK_SIGNING_SECRET`
- `AIRTABLE_API_KEY`
- `AIRTABLE_BASE_ID`
- `AIRTABLE_TABLE` (optional, defaults to `SlackUsers`)
- `PORT` (optional, defaults to `3000`)

## Running

Execute the bot with:

```bash
python slack_bot.py
```

The bot will DM every handle found in Airtable and open a modal asking two questions. Answers are saved back to Airtable with the Slack handle.
