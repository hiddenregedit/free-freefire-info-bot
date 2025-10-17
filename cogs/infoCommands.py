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
        self.session = aiohttp.ClientSession()
        self.config_data = self.load_config()
        self.cooldowns = {}

    # Convert UNIX timestamp safely
    def convert_unix_timestamp(self, timestamp: int) -> str:
        try:
            return datetime.utcfromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return "Not found"

    # Load config safely
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
                with open(CONFIG_FILE, "r") as f:
                    return json.load(f)
            except:
                return default_config
        return default_config

    # Save config
    def save_config(self):
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(self.config_data, f, indent=4, ensure_ascii=False)

    # Channel check
    async def is_channel_allowed(self, ctx):
        guild_id = str(ctx.guild.id)
        allowed_channels = self.config_data["servers"].get(guild_id, {}).get("info_channels", [])
        return not allowed_channels or str(ctx.channel.id) in allowed_channels

    # Main info command
    @commands.hybrid_command(name="info", description="Displays Free Fire player information")
    @app_commands.describe(uid="Enter player UID")
    async def player_info(self, ctx: commands.Context, uid: str):
        guild_id = str(ctx.guild.id)

        if not uid.isdigit():
            return await ctx.reply("❌ Invalid UID. Only numbers allowed.", mention_author=False)

        if not await self.is_channel_allowed(ctx):
            return await ctx.send("❌ This command is not allowed in this channel.", ephemeral=True)

        cooldown = self.config_data["global_settings"]["default_cooldown"]
        if guild_id in self.config_data["servers"]:
            cooldown = self.config_data["servers"][guild_id]["config"].get("cooldown", cooldown)

        # Cooldown check
        if ctx.author.id in self.cooldowns:
            last_used = self.cooldowns[ctx.author.id]
            if (datetime.now() - last_used).seconds < cooldown:
                remaining = cooldown - (datetime.now() - last_used).seconds
                return await ctx.send(f"⏳ Please wait {remaining}s before using this again.", ephemeral=True)

        self.cooldowns[ctx.author.id] = datetime.now()

        try:
            async with ctx.typing():
                async with self.session.get(f"{self.api_url}?uid={uid}") as response:
                    if response.status == 404:
                        return await ctx.send(f"❌ Player with UID `{uid}` not found.")
                    if response.status != 200:
                        return await ctx.send("⚠️ API error. Try again later.")
                    data = await response.json()

            # Extract info sections
            basic_info = data.get("basicInfo", {})
            captain_info = data.get("captainBasicInfo", {})
            clan_info = data.get("clanBasicInfo", {})
            credit_score_info = data.get("creditScoreInfo", {})
            pet_info = data.get("petInfo", {})
            profile_info = data.get("profileInfo", {})
            social_info = data.get("socialInfo", {})

            region = basic_info.get("region", "Not found")

            # === EMBED START ===
            embed = discord.Embed(
                title="🎯 PLAYER INFORMATION",
                color=discord.Color.blurple(),
                timestamp=datetime.now()
            )
            embed.set_thumbnail(url=ctx.author.display_avatar.url)

            embed.add_field(
                name="",
                value="🔗 **JOIN : [JOIN NOW](https://discord.gg/RXSh8MpsZA)**",
                inline=False
            )

            # ┌── ACCOUNT BASIC INFO ──┐
            embed.add_field(name="", value="\n".join([
                "**┌ 👤 ACCOUNT BASIC INFO**",
                f"├─ **Name:** {basic_info.get('nickname', 'Not found')}",
                f"├─ **UID:** `{uid}`",
                f"├─ **Level:** {basic_info.get('level', 'Not found')} (Exp: {basic_info.get('exp', '?')})",
                f"├─ **Region:** {region}",
                f"├─ **Likes:** {basic_info.get('liked', 'Not found')}",
                f"├─ **Honor Score:** {credit_score_info.get('creditScore', 'Not found')}",
                f"└─ **Signature:** {social_info.get('signature', 'None') or 'None'}"
            ]), inline=False)

            # ┌── ACCOUNT ACTIVITY ──┐
            embed.add_field(name="", value="\n".join([
                "**┌ 🎮 ACCOUNT ACTIVITY**",
                f"├─ **Most Recent OB:** {basic_info.get('releaseVersion', '?')}",
                f"├─ **Current BP Badges:** {basic_info.get('badgeCnt', 'Not found')}",
                f"├─ **BR Rank:** {basic_info.get('rankingPoints', 'Not found')}",
                f"├─ **CS Rank:** {basic_info.get('csRankingPoints', 'Not found')}",
                f"├─ **Created At:** {self.convert_unix_timestamp(int(basic_info.get('createAt', '0')))}",
                f"└─ **Last Login:** {self.convert_unix_timestamp(int(basic_info.get('lastLoginAt', '0')))}"
            ]), inline=False)

            # ┌── ACCOUNT OVERVIEW ──┐
            embed.add_field(name="", value="\n".join([
                "**┌ 👕 ACCOUNT OVERVIEW**",
                f"├─ **Avatar ID:** {profile_info.get('avatarId', 'Not found')}",
                f"├─ **Banner ID:** {basic_info.get('bannerId', 'Not found')}",
                f"├─ **Pin ID:** {captain_info.get('pinId', 'Not found') if captain_info else 'Default'}",
                f"└─ **Equipped Skills:** {profile_info.get('equipedSkills', 'Not found')}"
            ]), inline=False)

            # ┌── PET DETAILS ──┐
            embed.add_field(name="", value="\n".join([
                "**┌ 🐾 PET DETAILS**",
                f"├─ **Equipped?** {'Yes' if pet_info.get('isSelected') else 'Not Found'}",
                f"├─ **Pet Name:** {pet_info.get('name', 'Not Found')}",
                f"├─ **Pet Exp:** {pet_info.get('exp', 'Not Found')}",
                f"└─ **Pet Level:** {pet_info.get('level', 'Not Found')}"
            ]), inline=False)

            # ┌── GUILD INFO ──┐
            if clan_info:
                guild_info = [
                    "┌ 🛡️ **GUILD INFO**",
                    f"├─ **Guild Name:** {clan_info.get('clanName', 'Not found')}",
                    f"├─ **Guild ID:** `{clan_info.get('clanId', 'Not found')}`",
                    f"├─ **Guild Level:** {clan_info.get('clanLevel', 'Not found')}",
                    f"├─ **Live Members:** {clan_info.get('memberNum', 'Not found')}/{clan_info.get('capacity', '?')}",
                    "└─ 👑 **LEADER INFO:**",
                    f"  ├─ **Leader Name:** {captain_info.get('nickname', 'Not found')}",
                    f"  ├─ **Leader UID:** `{captain_info.get('accountId', 'Not found')}`",
                    f"  ├─ **Leader Level:** {captain_info.get('level', 'Not found')} (Exp: {captain_info.get('exp', '?')})",
                    f"  ├─ **Last Login:** {self.convert_unix_timestamp(int(captain_info.get('lastLoginAt', '0')))}",
                    f"  ├─ **Title:** {captain_info.get('title', 'Not found')}",
                    f"  ├─ **BP Badges:** {captain_info.get('badgeCnt', '?')}",
                    f"  ├─ **BR Rank:** {captain_info.get('rankingPoints', 'Not found')}",
                    f"  └─ **CS Rank:** {captain_info.get('csRankingPoints', 'Not found')}"
                ]
                embed.add_field(name="", value="\n".join(guild_info), inline=False)

            # Embed Footer + Image
            embed.set_image(url=f"https://profile.thug4ff.com/api/profile_card?uid={uid}")
            embed.set_footer(text="🔗 DEVELOPED BY TANVIR")

            # Send main embed only once
            await ctx.send(embed=embed)

            # 🖼️ Outfit image fetcher (ONLY once)
            try:
                image_url = f"{self.generate_url}?uid={uid}"
                async with self.session.get(image_url) as img_file:
                    if img_file.status == 200:
                        with io.BytesIO(await img_file.read()) as buf:
                            file = discord.File(buf, filename=f"outfit_{uuid.uuid4().hex[:8]}.png")
                            await ctx.send(file=file)
            except Exception as e:
                print("Outfit image failed:", e)

        except Exception as e:
            await ctx.send(f"❌ Unexpected error: `{e}`")
        finally:
            gc.collect()

    async def cog_unload(self):
        await self.session.close()


async def setup(bot):
    await bot.add_cog(InfoCommands(bot))
