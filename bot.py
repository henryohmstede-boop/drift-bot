import os
import json
import requests
import discord
from discord.ext import commands, tasks
from discord import ui
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN", "").strip()
API_KEY = os.getenv("BRAWL_API_KEY", "").strip()
MAIN_CLUB_TAG = os.getenv("CLUB_TAG", "").strip().upper()
ROLE_NAME = "Drifter"
VERIFIED_ROLE = "Verified"

STATS_CHANNEL_NAME = "join-a-club"
STATS_FILE = "club_stats_message.json"

CLUBS = [
    {"name": "Drift", "tag": MAIN_CLUB_TAG},
    # add more later like this:
    # {"name": "Drift 2", "tag": "#ABC123"},
]

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

def normalize_tag(tag: str) -> str:
    tag = tag.strip().upper().replace(" ", "")
    if not tag.startswith("#"):
        tag = "#" + tag
    return tag

def get_headers():
    return {"Authorization": f"Bearer {API_KEY}"}

def get_player(tag):
    tag = normalize_tag(tag)
    url = f"https://api.brawlstars.com/v1/players/%23{tag.replace('#', '')}"
    r = requests.get(url, headers=get_headers(), timeout=10)
    print("PLAYER:", r.status_code, r.text)
    return r.json() if r.status_code == 200 else None

def get_club(tag):
    tag = normalize_tag(tag)
    url = f"https://api.brawlstars.com/v1/clubs/%23{tag.replace('#', '')}"
    r = requests.get(url, headers=get_headers(), timeout=10)
    print("CLUB:", r.status_code, r.text)
    return r.json() if r.status_code == 200 else None

def ensure_json_file(path, default_value):
    if not os.path.exists(path):
        with open(path, "w") as f:
            json.dump(default_value, f, indent=2)

async def update_role(member, tag):
    drifter_role = discord.utils.get(member.guild.roles, name=ROLE_NAME)
    verified_role = discord.utils.get(member.guild.roles, name=VERIFIED_ROLE)
    player = get_player(tag)

    if not player:
        return False, "Invalid tag."

    if verified_role and verified_role not in member.roles:
        await member.add_roles(verified_role)

    club = player.get("club", {}).get("tag", "").upper()

    if club == MAIN_CLUB_TAG:
        if drifter_role and drifter_role not in member.roles:
            await member.add_roles(drifter_role)
        return True, "Linked! You now have access and got the Drifter role."
    else:
        if drifter_role and drifter_role in member.roles:
            await member.remove_roles(drifter_role)
        return True, "Linked! You now have access."

class VerifyModal(ui.Modal, title="Verify Your Brawl Stars Account"):
    player_tag = ui.TextInput(
        label="Enter your player tag",
        placeholder="#ABC123",
        required=True,
        max_length=15
    )

    async def on_submit(self, interaction: discord.Interaction):
        tag = normalize_tag(str(self.player_tag))
        ensure_json_file("links.json", {})

        with open("links.json", "r") as f:
            data = json.load(f)

        data[str(interaction.user.id)] = tag

        with open("links.json", "w") as f:
            json.dump(data, f, indent=2)

        success, message = await update_role(interaction.user, tag)

        if success:
            await interaction.response.send_message(message, ephemeral=True)
        else:
            await interaction.response.send_message(
                "That tag didn’t work. Check for O vs 0 and try again.",
                ephemeral=True
            )

class VerifyView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="Verify", style=discord.ButtonStyle.primary, custom_id="verify_button")
    async def verify_button(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(VerifyModal())

def build_stats_embed():
    embed = discord.Embed(
        title="📊 Club Stats",
        description="Live club stats for Drift clubs"
    )

    for club in CLUBS:
        club_data = get_club(club["tag"])
        if not club_data:
            embed.add_field(
                name=club["name"],
                value="Could not load club data.",
                inline=False
            )
            continue

        trophies = club_data.get("trophies", 0)
        required = club_data.get("requiredTrophies", 0)
        members = club_data.get("members", [])
        member_count = len(members)

        embed.add_field(
            name=club_data.get("name", club["name"]),
            value=(
                f"🏆 **Total Trophies:** {trophies:,}\n"
                f"👥 **Players:** {member_count}/30\n"
                f"🎯 **Min Trophies:** {required:,}"
            ),
            inline=False
        )

    return embed

async def get_stats_channel(guild: discord.Guild):
    channel = discord.utils.get(guild.text_channels, name=STATS_CHANNEL_NAME)
    return channel

async def get_saved_stats_message(channel: discord.TextChannel):
    ensure_json_file(STATS_FILE, {})

    with open(STATS_FILE, "r") as f:
        data = json.load(f)

    guild_id = str(channel.guild.id)
    message_id = data.get(guild_id)

    if not message_id:
        return None

    try:
        return await channel.fetch_message(message_id)
    except:
        return None

async def save_stats_message_id(guild_id: int, message_id: int):
    ensure_json_file(STATS_FILE, {})

    with open(STATS_FILE, "r") as f:
        data = json.load(f)

    data[str(guild_id)] = message_id

    with open(STATS_FILE, "w") as f:
        json.dump(data, f, indent=2)

async def refresh_stats_message(guild: discord.Guild):
    channel = await get_stats_channel(guild)
    if channel is None:
        print(f"No #{STATS_CHANNEL_NAME} channel in {guild.name}")
        return

    embed = build_stats_embed()
    message = await get_saved_stats_message(channel)

    if message:
        await message.edit(embed=embed)
    else:
        sent = await channel.send(embed=embed)
        await save_stats_message_id(guild.id, sent.id)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    bot.add_view(VerifyView())

    if not check_roles.is_running():
        check_roles.start()

    if not update_club_stats.is_running():
        update_club_stats.start()

@bot.event
async def on_message(message):
    if message.author.bot:
        return
    await bot.process_commands(message)

@bot.command()
async def setupverify(ctx):
    embed = discord.Embed(
        title="🔗 Verify Your Account",
        description=(
            "Click the button below and enter your Brawl Stars player tag.\n\n"
            "✅ Linked players get server access\n"
            "🎯 Club members also get the Drifter role\n\n"
            "Make sure your tag is correct: **0 ≠ O**"
        )
    )
    await ctx.send(embed=embed, view=VerifyView())

@bot.command()
async def setupclubstats(ctx):
    await refresh_stats_message(ctx.guild)
    await ctx.send("Club stats message is set up.", delete_after=5)

@tasks.loop(minutes=5)
async def update_club_stats():
    for guild in bot.guilds:
        try:
            await refresh_stats_message(guild)
        except Exception as e:
            print(f"Error updating club stats in {guild.name}: {e}")

@tasks.loop(minutes=5)
async def check_roles():
    ensure_json_file("links.json", {})

    with open("links.json", "r") as f:
        data = json.load(f)

    for guild in bot.guilds:
        for user_id, tag in data.items():
            member = guild.get_member(int(user_id))
            if member:
                try:
                    await update_role(member, tag)
                except Exception as e:
                    print(f"Error updating {member}: {e}")

bot.run(TOKEN)
