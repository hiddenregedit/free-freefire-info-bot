import discord
from discord.ext import commands

intents = discord.Intents.default()
intents.messages = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)

# --- Server Whitelist Check ---
@bot.event
async def on_guild_join(guild):
    allowed_servers = [1354065885140090910, 807419631388065822]  # replace with your server IDs
    if guild.id not in allowed_servers:
        await guild.leave()  # bot leaves unauthorized servers
# ------------------------------

@bot.event
async def on_ready():
    print(f"Bot is online as {bot.user}")

bot.run("MTM4OTQ4MDQ5ODI4MzQxMzUxNA.GkExp3.Bap2KVkbk6Ex9_WFJRp0nxs7DbqlVv-M3EKELo")
