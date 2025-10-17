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
        self.session = None
        self.config_data = self.load_config()
        self.cooldowns = {}

    async def cog_load(self):
        self.session = aiohttp.ClientSession()

    async def cog_unload(self):
        if self.session and not self.session.closed:
            await self.session.close()

    # ---------- CONFIG ----------
    def load_config(self):
        default = {
            "servers": {},
            "global_settings": {
                "default_all_channels": False,
                "default_cooldown": 30,
                "default_daily_limit": 30,
            },
        }
        if not os.path.exists(CONFIG_FILE):
            return default
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            cfg.setdefault("servers", {})
            cfg.setdefault("global_settings", default["global_settings"])
            return cfg
        except Exception:
            return default

    def save_config(self):
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.config_data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"[Save Error] {e}")

    # ---------- UTILITIES ----------
    def convert_unix_timestamp(self, timestamp: int) -> str:
        try:
            if not timestamp or timestamp <= 0:
                return "Unknown"
            return datetime.utcfromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return "Unknown"

    async def is_channel_allowed(self, ctx):
        guild_id = str(ctx.guild.id)
        allowed_channels = self.config_data["servers"].get(guild_id, {}).get("info_channels", [])
        if not allowed_channels:
            return True
        return str(ctx.channel.id) in allowed_channels

    def get_cooldown(self, guild_id):
        return (
            self.config_data["servers"]
            .get(guild_id, {})
            .get("config", {})
            .get("cooldown", self.config_data["global_settings"]["default_cooldown"])
        )

    def is_on_cooldown(self, user_id, cooldown):
        now = datetime.now()
        if user_id not in self.cooldowns:
            return False
        return (now - self.cooldowns[user_id]).total_seconds() < cooldown

    # ---------- MAIN INFO COMMAND ----------
    @commands.hybrid_command(name="info", description="Display a Free Fire player's information.")
    @app_commands.describe(uid="Enter the player's Free Fire UID.")
    async def player_info(self, ctx, uid: str):
        guild_id = str(ctx.guild.id)

        if not uid.isdigit() or len(uid) < 6:
            return await ctx.reply("❌ Invalid UID! Use digits only (at least 6).", mention_author=False)

        if not await self.is_channel_allowed(ctx):
            return await ctx.reply("🚫 This command is not allowed in this channel.", mention_author=False)

        cooldown = self.get_cooldown(guild_id)
        if self.is_on_cooldown(ctx.author.id, cooldown):
            remaining = cooldown - int((datetime.now() - self.cooldowns[ctx.author.id]).total_seconds())
            return await ctx.reply(f"⌛ Please wait {remaining}s before using again.", mention_author=False)

        self.cooldowns[ctx.author.id] = datetime.now()

        try:
            async with ctx.typing():
                async with self.session.get(f"{self.api_url}?uid={uid}", timeout=10) as r:
                    if r.status == 404:
                        return await self._send_player_not_found(ctx, uid)
                    if r.status != 200:
                        return await self._send_api_error(ctx)
                    data = await r.json()

            basic = data.get("basicInfo", {})
            captain = data.get("captainBasicInfo", {})
            clan = data.get("clanBasicInfo", {})
            credit = data.get("creditScoreInfo", {})
            pet = data.get("petInfo", {})
            social = data.get("socialInfo", {})

            # 🎨 Embed
            embed = discord.Embed(
                title=f"🎯 {basic.get('nickname', 'Unknown')} — UID: {uid}",
                color=discord.Color.blurple(),
                timestamp=datetime.now(),
            )
            embed.set_thumbnail(url=f"https://profile.thug4ff.com/api/profile_card?uid={uid}")
            embed.add_field(
                name="👤 ACCOUNT INFO",
                value="\n".join([
                    f"**Level:** {basic.get('level', '?')} (Exp: {basic.get('exp', '?')})",
                    f"**Region:** {basic.get('region', '?')}",
                    f"**Likes:** ❤️ {basic.get('liked', '?')}",
                    f"**Honor:** {credit.get('creditScore', '?')}",
                    f"**Signature:** {social.get('signature', 'None') or 'None'}",
                ]),
                inline=False,
            )

            embed.add_field(
                name="⚙️ ACTIVITY",
                value="\n".join([
                    f"**OB Version:** {basic.get('releaseVersion', '?')}",
                    f"**BP Badges:** {basic.get('badgeCnt', '?')}",
                    f"**BR Rank:** {basic.get('rankingPoints', '?')}",
                    f"**CS Rank:** {basic.get('csRankingPoints', '?')}",
                    f"**Created:** {self.convert_unix_timestamp(int(basic.get('createAt', 0)))}",
                    f"**Last Login:** {self.convert_unix_timestamp(int(basic.get('lastLoginAt', 0)))}",
                ]),
                inline=False,
            )

            embed.add_field(
                name="🐾 PET INFO",
                value="\n".join([
                    f"**Pet Name:** {pet.get('name', 'N/A')}",
                    f"**Level:** {pet.get('level', 'N/A')}",
                    f"**Exp:** {pet.get('exp', 'N/A')}",
                    f"**Equipped:** {'✅ Yes' if pet.get('isSelected') else '❌ No'}",
                ]),
                inline=False,
            )

            # 🛡️ Guild Info + Leader Details
            if clan:
                gtext = [
                    f"**Guild Name:** {clan.get('clanName', '?')}",
                    f"**Guild ID:** `{clan.get('clanId', '?')}`",
                    f"**Level:** {clan.get('clanLevel', '?')}",
                    f"**Members:** {clan.get('memberNum', '?')}/{clan.get('capacity', '?')}",
                ]
                if captain:
                    gtext += [
                        "",
                        "👑 **LEADER INFO**",
                        f"**Name:** {captain.get('nickname', '?')}",
                        f"**UID:** `{captain.get('accountId', '?')}`",
                        f"**Level:** {captain.get('level', '?')} (Exp: {captain.get('exp', '?')})",
                        f"**Last Login:** {self.convert_unix_timestamp(int(captain.get('lastLoginAt', 0)))}",
                        f"**Title:** {captain.get('title', '?')}",
                        f"**BP Badges:** {captain.get('badgeCnt', '?')}",
                        f"**BR Rank:** {captain.get('rankingPoints', '?')}",
                        f"**CS Rank:** {captain.get('csRankingPoints', '?')}",
                    ]
                embed.add_field(name="🛡️ GUILD INFO", value="\n".join(gtext), inline=False)

            embed.set_footer(text="🔗 Developed by Tanvir | RXSh8MpsZA")

            await ctx.send(embed=embed)

            # 🧾 Outfit Image (New API)
            try:
                async with self.session.get(f"{self.generate_url}?uid={uid}", timeout=15) as resp:
                    if resp.status == 200:
                        content_type = resp.headers.get("Content-Type", "")
                        if "image" in content_type:
                            buf = io.BytesIO(await resp.read())
                            file = discord.File(buf, filename=f"outfit_{uuid.uuid4().hex[:8]}.png")
                            await ctx.send(file=file)
                        elif "application/json" in content_type:
                            js = await resp.json()
                            link = js.get("image") or js.get("url")
                            if link:
                                async with self.session.get(link, timeout=15) as img:
                                    if img.status == 200:
                                        buf = io.BytesIO(await img.read())
                                        file = discord.File(buf, filename=f"outfit_{uuid.uuid4().hex[:8]}.png")
                                        await ctx.send(file=file)
                                    else:
                                        await ctx.send("⚠️ Image link not reachable.")
                            else:
                                await ctx.send("❌ No image link found in response.")
                        else:
                            await ctx.send("⚠️ Unexpected outfit image format.")
                    else:
                        await ctx.send("⚠️ Outfit image API error.")
            except Exception as e:
                print(f"[Outfit Image Error] {e}")
                await ctx.send("⚠️ Failed to load outfit image.")
        except asyncio.TimeoutError:
            await ctx.send("⏱️ Request timed out.")
        except Exception as e:
            await ctx.send(f"⚠️ Unexpected error: `{e}`")
        finally:
            gc.collect()

    async def _send_player_not_found(self, ctx, uid):
        embed = discord.Embed(
            title="❌ Player Not Found",
            description=f"UID `{uid}` not found or unavailable.",
            color=discord.Color.red(),
        )
        await ctx.send(embed=embed)

    async def _send_api_error(self, ctx):
        embed = discord.Embed(
            title="⚠️ API Error",
            description="Free Fire API not responding. Try again later.",
            color=discord.Color.orange(),
        )
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(InfoCommands(bot))
