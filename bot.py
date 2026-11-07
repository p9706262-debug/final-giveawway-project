import asyncio
import json
import os
import random
import re
import time

import discord
from discord import app_commands
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
DATA_FILE = "giveaways.json"


# ---------- storage (simple JSON file) ----------
def load_data() -> dict:
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_data() -> None:
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(giveaways, f, indent=2)


# message_id (str) -> giveaway info
giveaways: dict = load_data()
background_tasks: set = set()


# ---------- helpers ----------
def parse_duration(text: str):
    """'30s', '10m', '2h', '1d' -> seconds. Returns None if invalid."""
    match = re.fullmatch(r"(\d+)\s*([smhd])", text.strip().lower())
    if not match:
        return None
    amount, unit = int(match.group(1)), match.group(2)
    return amount * {"s": 1, "m": 60, "h": 3600, "d": 86400}[unit]


def build_embed(g: dict, ended: bool = False) -> discord.Embed:
    if ended:
        embed = discord.Embed(
            title=f"🎁 {g['prize']}",
            description=(
                "**This giveaway has ended!**\n"
                "Press **Check My Luck** to see if you won."
            ),
            color=discord.Color.red(),
        )
    else:
        embed = discord.Embed(
            title=f"🎁 {g['prize']}",
            description=(
                "Press **Enter Giveaway** to join!\n"
                f"Ends: <t:{g['end_ts']}:R> (<t:{g['end_ts']}:f>)"
            ),
            color=discord.Color.green(),
        )
    embed.add_field(name="Winners", value=str(g["winner_count"]))
    embed.add_field(name="Entries", value=str(len(g["entries"])))
    embed.set_footer(text=f"Hosted by {g['host_name']}")
    return embed


# ---------- buttons (persistent, survive restarts) ----------
class EnterView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Enter Giveaway",
        emoji="🎉",
        style=discord.ButtonStyle.green,
        custom_id="giveaway:enter",
    )
    async def enter(self, interaction: discord.Interaction, button: discord.ui.Button):
        g = giveaways.get(str(interaction.message.id))
        if g is None or g["ended"] or time.time() >= g["end_ts"]:
            await interaction.response.send_message(
                "This giveaway has already ended.", ephemeral=True
            )
            return

        if interaction.user.id in g["entries"]:
            await interaction.response.send_message(
                "You already entered this giveaway! 👍", ephemeral=True
            )
            return

        g["entries"].append(interaction.user.id)
        save_data()
        await interaction.response.send_message(
            "You're in! Good luck 🍀", ephemeral=True
        )
        # update the entries counter on the giveaway message
        await interaction.message.edit(embed=build_embed(g))


class CheckView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Check My Luck",
        emoji="🍀",
        style=discord.ButtonStyle.blurple,
        custom_id="giveaway:check",
    )
    async def check(self, interaction: discord.Interaction, button: discord.ui.Button):
        g = giveaways.get(str(interaction.message.id))
        if g is None:
            await interaction.response.send_message(
                "I can't find this giveaway.", ephemeral=True
            )
            return

        uid = interaction.user.id
        if uid not in g["entries"]:
            msg = "You didn't enter this giveaway."
        elif uid in g["winners"]:
            msg = "Hey, you won! 🎉 Give us a treat ❤️"
        else:
            msg = "You lost 😂"
        await interaction.response.send_message(msg, ephemeral=True)


# ---------- bot ----------
class GiveawayBot(discord.Client):
    def __init__(self):
        super().__init__(intents=discord.Intents.default())
        self.tree = app_commands.CommandTree(self)
        self._started = False

    async def setup_hook(self):
        # register the buttons so they keep working after a restart
        self.add_view(EnterView())
        self.add_view(CheckView())
        await self.tree.sync()

    async def on_ready(self):
        print(f"Logged in as {self.user}")
        if self._started:
            return
        self._started = True
        # resume timers for giveaways that were running when the bot stopped
        for message_id, g in giveaways.items():
            if not g["ended"]:
                spawn(wait_and_end(message_id))


bot = GiveawayBot()


def spawn(coro):
    task = asyncio.create_task(coro)
    background_tasks.add(task)
    task.add_done_callback(background_tasks.discard)


async def wait_and_end(message_id: str):
    g = giveaways[message_id]
    await asyncio.sleep(max(0, g["end_ts"] - time.time()))
    await end_giveaway(message_id)


async def end_giveaway(message_id: str):
    g = giveaways.get(message_id)
    if g is None or g["ended"]:
        return

    g["ended"] = True
    count = min(g["winner_count"], len(g["entries"]))
    g["winners"] = random.sample(g["entries"], count)
    save_data()

    try:
        channel = bot.get_channel(g["channel_id"]) or await bot.fetch_channel(
            g["channel_id"]
        )
        message = await channel.fetch_message(int(message_id))
        await message.edit(embed=build_embed(g, ended=True), view=CheckView())
        await channel.send(
            f"🎉 The giveaway for **{g['prize']}** has ended! "
            f"Press **Check My Luck** on the giveaway message above.",
            reference=message,
        )
    except discord.HTTPException as e:
        print(f"Could not update giveaway {message_id}: {e}")


# ---------- slash command ----------
@bot.tree.command(name="giveaway", description="Start a giveaway (admins only)")
@app_commands.describe(
    prize="What are you giving away?",
    winners="How many winners? (1-20)",
    duration="How long can people enter? e.g. 30s, 10m, 2h, 1d",
)
@app_commands.default_permissions(manage_guild=True)
@app_commands.checks.has_permissions(manage_guild=True)
@app_commands.guild_only()
async def giveaway(
    interaction: discord.Interaction,
    prize: app_commands.Range[str, 1, 100],
    winners: app_commands.Range[int, 1, 20],
    duration: str,
):
    seconds = parse_duration(duration)
    if seconds is None or seconds < 10 or seconds > 30 * 86400:
        await interaction.response.send_message(
            "Invalid duration. Use something like `30s`, `10m`, `2h` or `1d` "
            "(minimum 10s, maximum 30d).",
            ephemeral=True,
        )
        return

    g = {
        "prize": prize,
        "winner_count": winners,
        "end_ts": int(time.time()) + seconds,
        "channel_id": interaction.channel_id,
        "host_name": interaction.user.display_name,
        "entries": [],
        "winners": [],
        "ended": False,
    }

    await interaction.response.send_message(embed=build_embed(g), view=EnterView())
    message = await interaction.original_response()

    giveaways[str(message.id)] = g
    save_data()
    spawn(wait_and_end(str(message.id)))


@giveaway.error
async def giveaway_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message(
            "Only admins (Manage Server permission) can start giveaways.",
            ephemeral=True,
        )
    else:
        raise error


if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("Missing DISCORD_TOKEN. Copy .env.example to .env and add your token.")
    bot.run(TOKEN)
