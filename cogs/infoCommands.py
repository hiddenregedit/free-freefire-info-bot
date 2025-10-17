import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
from datetime import datetime, timedelta
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
        except Exception as e:
            print(f"[Config Error] {e}")
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

    # ---------- COMMANDS ----------
    @commands.hybrid_command(name="setinfochannel", description="Allow a channel for !info commands")
    @commands.has_permissions(administrator=True)
    async def set_info_channel(self, ctx, channel: discord.TextChannel):
        guild_id = str(ctx.guild.id)
        self.config_data["servers"].setdefault(guild_id, {"info_channels": [], "config": {}})
        ch_list = self.config_data["servers"][guild_id]["info_channels"]
        if str(channel.id) not in ch_list:
            ch_list.append(str(channel.id))
            self.save_config()
            await ctx.send(f"✅ {channel.mention} added as allowed for `!info`")
        else:
            await ctx.send(f"ℹ️ {channel.mention} is already allowed.")

    @commands.hybrid_command(name="removeinfochannel", description="Remove an allowed info channel")
    @commands.has_permissions(administrator=True)
    async def remove_info_channel(self, ctx, channel: discord.TextChannel):
        guild_id = str(ctx.guild.id)
        if guild_id not in self.config_data["servers"]:
            return await ctx.send("ℹ️ No config found for this server.")
        ch_list = self.config_data["servers"][guild_id]["info_channels"]
        if str(channel.id) in ch_list:
            ch_list.remove(str(channel.id))
            self.save_config()
            await ctx.send(f"✅ {channel.mention} removed from allowed channels.")
        else:
            await ctx.send(f"❌ {channel.mention} was not allowed.")

    @commands.hybrid_command(name="infochannels", description="List allowed !info channels")
    async def list_info_channels(self, ctx):
        guild_id = str(ctx.guild.id)
        server_cfg = self.config_data["servers"].get(guild_id, {})
        channels = server_cfg.get("info_channels", [])
        cooldown = self.get_cooldown(guild_id)

        if channels:
            desc = "\n".join(
                f"• {ctx.guild.get_channel(int(cid)).mention if ctx.guild.get_channel(int(cid)) else f'ID: {cid}'}"
                for cid in channels
            )
        else:
            desc = "All channels are allowed (no restriction set)."

        embed = discord.Embed(
            title="📜 Allowed Info Channels",
            description=desc,
            color=discord.Color.blue(),
        )
        embed.set_footer(text=f"Cooldown: {cooldown}s")
        await ctx.send(embed=embed)

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
            profile = data.get("profileInfo", {})
            social = data.get("socialInfo", {})

            embed = discord.Embed(
                title=f"🎯 PLAYER INFO: {basic.get('nickname', 'Unknown')}",
                color=discord.Color.blurple(),
                timestamp=datetime.now(),
            )
            embed.set_thumbnail(url=ctx.author.display_avatar.url)
            embed.add_field(
                name="🔗 JOIN",
                value="[JOIN NOW](https://discord.gg/RXSh8MpsZA)",
                inline=False,
            )

            embed.add_field(
                name="👤 ACCOUNT BASIC INFO",
                value="\n".join([
                    f"**Name:** {basic.get('nickname', 'Unknown')}",
                    f"**UID:** `{uid}`",
                    f"**Level:** {basic.get('level', '?')} (Exp: {basic.get('exp', '?')})",
                    f"**Region:** {basic.get('region', '?')}",
                    f"**Likes:** {basic.get('liked', '?')}",
                    f"**Honor Score:** {credit.get('creditScore', '?')}",
                    f"**Signature:** {social.get('signature', 'None') or 'None'}",
                ]),
                inline=False,
            )

            embed.add_field(
                name="🎮 ACCOUNT ACTIVITY",
                value="\n".join([
                    f"**Most Recent OB:** {basic.get('releaseVersion', '?')}",
                    f"**Current BP Badges:** {basic.get('badgeCnt', '?')}",
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
                    f"**Equipped:** {'Yes' if pet.get('isSelected') else 'No'}",
                ]),
                inline=False,
            )

            if clan:
                gtext = [
                    f"**Guild Name:** {clan.get('clanName', '?')}",
                    f"**Guild ID:** `{clan.get('clanId', '?')}`",
                    f"**Level:** {clan.get('clanLevel', '?')}",
                    f"**Members:** {clan.get('memberNum', '?')}/{clan.get('capacity', '?')}",
                ]
                if captain:
                    gtext.append(f"**Leader:** {captain.get('nickname', '?')} (UID: {captain.get('accountId', '?')})")
                embed.add_field(name="🛡️ GUILD INFO", value="\n".join(gtext), inline=False)

            embed.set_image(url=f"https://profile.thug4ff.com/api/profile_card?uid={uid}")
            embed.set_footer(text="🔗 Developed by Tanvir")
            await ctx.send(embed=embed)

            # ---- Outfit Image ----
            try:
                img_url = f"{self.generate_url}?uid={uid}"
                async with self.session.get(img_url, timeout=15) as img_resp:
                    if img_resp.status == 200:
                        content_type = img_resp.headers.get("Content-Type", "")
                        if "application/json" in content_type:
                            data = await img_resp.json()
                            image_link = data.get("image") or data.get("url")
                            if image_link:
                                async with self.session.get(image_link, timeout=15) as img_file:
                                    if img_file.status == 200:
                                        buf = io.BytesIO(await img_file.read())
                                        file = discord.File(buf, filename=f"outfit_{uuid.uuid4().hex[:8]}.png")
                                        await ctx.send(file=file)
                                    else:
                                        await ctx.send("⚠️ Outfit image link not responding.")
                            else:
                                await ctx.send("❌ Outfit image not found in API response.")
                        elif "image" in content_type:
                            buf = io.BytesIO(await img_resp.read())
                            file = discord.File(buf, filename=f"outfit_{uuid.uuid4().hex[:8]}.png")
                            await ctx.send(file=file)
                        else:
                            await ctx.send("❌ Unexpected API format for outfit image.")
                    else:
                        await ctx.send("⚠️ Outfit image API returned an error.")
            except Exception as e:
                print(f"[Outfit Image Error] {e}")
                await ctx.send("⚠️ Failed to load outfit image. Try again later.")

        except asyncio.TimeoutError:
            await ctx.send("⏱️ Request timed out. Please try again later.")
        except Exception as e:
            await ctx.send(f"⚠️ Unexpected error: `{e}`")
        finally:
            gc.collect()

    async def _send_player_not_found(self, ctx, uid):
        embed = discord.Embed(
            title="❌ Player Not Found",
            description=f"UID `{uid}` not found or unavailable.\nTry again later.",
            color=discord.Color.red(),
        )
        await ctx.send(embed=embed)

    async def _send_api_error(self, ctx):
        embed = discord.Embed(
            title="⚠️ API Error",
            description="Free Fire API is not responding. Try again later.",
            color=discord.Color.orange(),
        )
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(InfoCommands(bot))
