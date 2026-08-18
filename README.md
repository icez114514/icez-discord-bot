# Termux Discord Test Bot

This minimal bot registers a `/ping` slash command and replies with its latency.

## Run in Termux

```bash
pkg update
pkg install python git
python -m pip install -r requirements.txt
export DISCORD_TOKEN='paste-your-bot-token-here'
termux-wake-lock
python bot.py
```

When the log shows `Logged in as ...`, open a Discord server containing the bot
and run `/ping`.

Stop the bot with `Ctrl+C`. Release the wake lock when finished:

```bash
termux-wake-unlock
```

Never commit or share the bot token. If it is exposed, reset it immediately in
the Discord Developer Portal.
