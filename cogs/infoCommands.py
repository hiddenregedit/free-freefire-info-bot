import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
from datetime import datetime
import json
import os
import asyncio
import io
import uuid
import gc

CONFIG_FILE = "info_channels.json"


class InfoCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.api_url = "https://ff-info-nine.vercel.app/info"
        self.generate_url = "https://profile.thug4ff.com/api/profile"
        self.session = None  # ✅ FIX: delay session creation for better lifecycle handling
        self.config_data = self.load_config()
        self.cooldowns = {}

    async def cog_load(self):
        """Initialize aiohttp session once cog is loaded"""
        self.session = aiohttp.ClientSession()

    async def cog_unload(self):
        """Ensure proper session cleanup"""
        if self.session and not self.session.closed:
            await self.session.close()

    # ========================
    # CONFIG MANAGEMENT
    # ========================
    def load_config(self):
        default_config = {
            "servers": {},
            "global_settings": {
                "default_all_channels": False,
                "default_cooldown": 30,
                "default_daily_limit": 30
            }
        }
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    data.setdefault("servers", {})
                    data.setdefault("global_settings", default_config["global_settings"])
                    return data
            except (json.JSONDecodeError, IOError):
                return default_config
        return default_config

    def save_config(self):
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.config_data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print("Error saving config:", e)

    # ========================
    # HELPER FUNCTIONS
    # ========================
    def convert_unix_timestamp(self, timestamp: int) -> str:
        try:
            if timestamp <= 0:
                return "N/A"
            return datetime.utcfromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return "N/A"

    async def is_channel_allowed(self, ctx):
        try:
            guild_id = str(ctx.guild.id)
            allowed_channels = self.config_data["servers"].get(guild_id, {}).get("info_channels", [])
            if not allowed_channels:
                return True
            return str(ctx.channel.id) in allowed_channels
        except Exception as e:
            print("Error checking channel:", e)
            return False

    # ========================
    # ADMIN COMMANDS
    # ========================
    @commands.hybrid_command(name="setinfochannel", description="Allow a channel for !info commands")
    @commands.has_permissions(administrator=True)
    async def set_info_channel(self, ctx, channel: discord.TextChannel):
        guild_id = str(ctx.guild.id)
        self.config_data["servers"].setdefault(guild_id, {"info_channels": [], "config": {}})
        channels = self.config_data["servers"][guild_id]["info_channels"]

        if str(channel.id) not in channels:
            channels.append(str(channel.id))
            self.save_config()
            await ctx.send(f"✅ {channel.mention} is now allowed for `!info` commands")
        else:
            await ctx.send(f"ℹ️ {channel.mention} is already allowed.")

    @commands.hybrid_command(name="removeinfochannel", description="Remove a channel from allowed list")
    @commands.has_permissions(administrator=True)
    async def remove_info_channel(self, ctx, channel: discord.TextChannel):
        guild_id = str(ctx.guild.id)
        server = self.config_data["servers"].get(guild_id, {})
        channels = server.get("info_channels", [])
        if str(channel.id) in channels:
            channels.remove(str(channel.id))
            self.save_config()
            await ctx.send(f"✅ Removed {channel.mention} from allowed channels.")
        else:
            await ctx.send("❌ That channel isn’t in the list.")

    @commands.hybrid_command(name="infochannels", description="List channels allowed for info command")
    async def list_info_channels(self, ctx):
        guild_id = str(ctx.guild.id)
        server = self.config_data["servers"].get(guild_id, {})
        allowed = server.get("info_channels", [])
        cooldown = server.get("config", {}).get("cooldown", self.config_data["global_settings"]["default_cooldown"])

        if allowed:
            channels = []
            for cid in allowed:
                ch = ctx.guild.get_channel(int(cid))
                channels.append(f"• {ch.mention if ch else f'ID: {cid}'}")
            desc = "\n".join(channels)
        else:
            desc = "All channels are allowed (no restriction set)."

        embed = discord.Embed(title="Allowed Channels", description=desc, color=discord.Color.blue())
        embed.set_footer(text=f"Cooldown per user: {cooldown}s")
        await ctx.send(embed=embed)

    # ========================
    # MAIN COMMAND
    # ========================
    @commands.hybrid_command(name="info", description="Get Free Fire player info")
    @app_commands.describe(uid="Enter Free Fire player UID")
    async def player_info(self, ctx, uid: str):
        guild_id = str(ctx.guild.id)

        if not uid.isdigit() or len(uid) < 6:
            return await ctx.reply("❌ Invalid UID! Must be numeric and at least 6 digits.", mention_author=False)

        if not await self.is_channel_allowed(ctx):
            return await ctx.reply("⚠️ This command isn’t allowed in this channel.", mention_author=False)

        # Cooldown system
        cooldown = self.config_data["global_settings"]["default_cooldown"]
        guild_cfg = self.config_data["servers"].get(guild_id, {}).get("config", {})
        cooldown = guild_cfg.get("cooldown", cooldown)

        if ctx.author.id in self.cooldowns:
            elapsed = (datetime.now() - self.cooldowns[ctx.author.id]).seconds
            if elapsed < cooldown:
                return await ctx.reply(f"⏳ Please wait {cooldown - elapsed}s before using this again.")

        self.cooldowns[ctx.author.id] = datetime.now()

        try:
            async with ctx.typing():
                async with self.session.get(f"{self.api_url}?uid={uid}") as r:
                    if r.status == 404:
                        return await ctx.send(f"❌ Player with UID `{uid}` not found.")
                    if r.status != 200:
                        return await ctx.send("⚠️ API error. Try again later.")
                    data = await r.json()

            # Extract info
            basic = data.get("basicInfo", {})
            captain = data.get("captainBasicInfo", {})
            clan = data.get("clanBasicInfo", {})
            pet = data.get("petInfo", {})
            profile = data.get("profileInfo", {})
            credit = data.get("creditScoreInfo", {})
            social = data.get("socialInfo", {})

            embed = discord.Embed(
                title="🎯 Player Information",
                color=discord.Color.blurple(),
                timestamp=datetime.now()
            )
            embed.set_thumbnail(url=ctx.author.display_avatar.url)

            embed.add_field(
                name="👤 Account Info",
                value="\n".join([
                    f"**Name:** {basic.get('nickname', 'N/A')}",
                    f"**UID:** `{uid}`",
                    f"**Level:** {basic.get('level', 'N/A')}",
                    f"**Region:** {basic.get('region', 'N/A')}",
                    f"**Likes:** {basic.get('liked', 'N/A')}",
                    f"**Honor:** {credit.get('creditScore', 'N/A')}",
                    f"**Signature:** {social.get('signature', 'None') or 'None'}"
                ]),
                inline=False
            )

            embed.add_field(
                name="🎮 Activity",
                value="\n".join([
                    f"**Version:** {basic.get('releaseVersion', '?')}",
                    f"**Badges:** {basic.get('badgeCnt', '?')}",
                    f"**Created:** {self.convert_unix_timestamp(int(basic.get('createAt', '0')))}",
                    f"**Last Login:** {self.convert_unix_timestamp(int(basic.get('lastLoginAt', '0')))}"
                ]),
                inline=False
            )

            if clan:
                clan_lines = [
                    f"**Guild Name:** {clan.get('clanName', 'N/A')}",
                    f"**Guild ID:** `{clan.get('clanId', 'N/A')}`",
                    f"**Level:** {clan.get('clanLevel', 'N/A')}",
                    f"**Members:** {clan.get('memberNum', '?')}/{clan.get('capacity', '?')}"
                ]
                if captain:
                    clan_lines.append(f"**Leader:** {captain.get('nickname', 'N/A')} (`{captain.get('accountId', 'N/A')}`)")
                embed.add_field(name="🛡️ Guild Info", value="\n".join(clan_lines), inline=False)

            embed.set_image(url=f"https://profile.thug4ff.com/api/profile_card?uid={uid}")
            embed.set_footer(text="🔗 Developed by Tanvir")

            await ctx.send(embed=embed)

            # ✅ Send outfit image separately (no crash)
            try:
                async with self.session.get(f"{self.generate_url}?uid={uid}") as img:
                    if img.status == 200:
                        buf = io.BytesIO(await img.read())
                        await ctx.send(file=discord.File(buf, filename=f"outfit_{uid}.png"))
            except Exception as e:
                print("Image fetch failed:", e)

        except Exception as e:
            await ctx.send(f"❌ Unexpected error: `{e}`")
        finally:
            gc.collect()


async def setup(bot):
    await bot.add_cog(InfoCommands(bot))
