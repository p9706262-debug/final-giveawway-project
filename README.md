# Giveaway Bot

A free Discord giveaway bot.

- Admins start a giveaway with `/giveaway prize winners duration`
- Members press **Enter Giveaway** (one entry per person)
- When time is up, the bot picks the winners and shows **Check My Luck**
- Winners see: "Hey, you won! 🎉 Give us a treat ❤️" / others see: "You lost 😂"

## Setup

1. Create an app at https://discord.com/developers/applications, open the **Bot** tab, and copy the token.
2. Invite the bot: **OAuth2 → URL Generator**, tick `bot` and `applications.commands`, then give it permissions: View Channels, Send Messages, Embed Links, Read Message History.
3. Install and run:

```bash
pip install -r requirements.txt
cp .env.example .env     # then put your token in .env
python bot.py
```

## Usage

`/giveaway prize:Nitro winners:2 duration:10m`

Duration examples: `30s`, `10m`, `2h`, `1d`. Only members with **Manage Server** can start giveaways.

## Notes

- Giveaway data is saved in `giveaways.json`, so running giveaways survive restarts.
- Never commit your `.env` file or share your token.
