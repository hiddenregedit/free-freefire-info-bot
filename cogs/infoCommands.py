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

    # -------------------
    # Utilities
    # -------------------
    def convert_unix_timestamp(self, timestamp: int) -> str:
        try:
            if not timestamp or int(timestamp) == 0:
                return "Unknown"
            return datetime.utcfromtimestamp(int(timestamp)).strftime('%Y-%m-%d %H:%M:%S')
        except Exception:
            return "Unknown"

    def load_config(self):
        default = {
            "servers": {},
            "global_settings": {
                "default_all_channels": False,
                "default_cooldown": 30,
                "default_daily_limit": 30
            }
        }
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    cfg = json.load(f)
                    cfg.setdefault("global_settings", default["global_settings"])
                    cfg.setdefault("servers", {})
                    return cfg
            except Exception as e:
                print("Config load error:", e)
        return default

    def save_config(self):
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.config_data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print("Save config error:", e)

    async def is_channel_allowed(self, ctx):
        try:
            guild_id = str(ctx.guild.id)
            allowed = self.config_data["servers"].get(guild_id, {}).get("info_channels", [])
            return not allowed or str(ctx.channel.id) in allowed
        except Exception as e:
            print("Channel check error:", e)
            return False

    # -------------------
    # Channel commands
    # -------------------
    @commands.hybrid_command(name="setinfochannel", description="Allow a channel for !info commands")
    @commands.has_permissions(administrator=True)
    async def set_info_channel(self, ctx: commands.Context, channel: discord.TextChannel):
        guild_id = str(ctx.guild.id)
        self.config_data["servers"].setdefault(guild_id, {"info_channels": [], "config": {}})
        if str(channel.id) not in self.config_data["servers"][guild_id]["info_channels"]:
            self.config_data["servers"][guild_id]["info_channels"].append(str(channel.id))
            self.save_config()
            await ctx.send(f"✅ {channel.mention} is now allowed for `!info` commands")
        else:
            await ctx.send(f"ℹ️ {channel.mention} is already allowed for `!info` commands")

    @commands.hybrid_command(name="removeinfochannel", description="Remove a channel from !info commands")
    @commands.has_permissions(administrator=True)
    async def remove_info_channel(self, ctx: commands.Context, channel: discord.TextChannel):
        guild_id = str(ctx.guild.id)
        if guild_id in self.config_data["servers"]:
            if str(channel.id) in self.config_data["servers"][guild_id]["info_channels"]:
                self.config_data["servers"][guild_id]["info_channels"].remove(str(channel.id))
                self.save_config()
                await ctx.send(f"✅ {channel.mention} has been removed from allowed channels")
            else:
                await ctx.send(f"❌ {channel.mention} is not in the list of allowed channels")
        else:
            await ctx.send("ℹ️ This server has no saved configuration")

    @commands.hybrid_command(name="infochannels", description="List allowed channels")
    async def list_info_channels(self, ctx: commands.Context):
        guild_id = str(ctx.guild.id)
        channels = self.config_data["servers"].get(guild_id, {}).get("info_channels", [])
        desc = "\n".join(f"• <#{cid}>" for cid in channels) if channels else "All channels are allowed."
        embed = discord.Embed(title="Allowed Channels", description=desc, color=discord.Color.blurple())
        await ctx.send(embed=embed)

    # -------------------
    # Main command
    # -------------------
    @commands.hybrid_command(name="info", description="Displays detailed Free Fire player information")
    @app_commands.describe(uid="FREE FIRE PLAYER UID")
    async def player_info(self, ctx: commands.Context, uid: str):
        guild_id = str(ctx.guild.id)

        if not uid.isdigit() or len(uid) < 6:
            return await ctx.reply("❌ Invalid UID! It must be numeric and at least 6 digits.", mention_author=False)

        if not await self.is_channel_allowed(ctx):
            return await ctx.send("⚠️ This command is not allowed in this channel.", ephemeral=True)

        cooldown = self.config_data["global_settings"]["default_cooldown"]
        if guild_id in self.config_data["servers"]:
            cooldown = self.config_data["servers"][guild_id]["config"].get("cooldown", cooldown)

        last = self.cooldowns.get(ctx.author.id)
        if last and (datetime.now() - last).seconds < cooldown:
            remaining = cooldown - (datetime.now() - last).seconds
            return await ctx.send(f"⏳ Please wait {remaining}s before using this command again.", ephemeral=True)
        self.cooldowns[ctx.author.id] = datetime.now()

        try:
            async with ctx.typing():
                async with self.session.get(f"{self.api_url}?uid={uid}") as resp:
                    if resp.status == 404:
                        return await self._send_player_not_found(ctx, uid)
                    if resp.status != 200:
                        return await self._send_api_error(ctx)
                    data = await resp.json()

            basic = data.get("basicInfo", {})
            captain = data.get("captainBasicInfo", {})
            clan = data.get("clanBasicInfo", {})
            credit = data.get("creditScoreInfo", {})
            pet = data.get("petInfo", {})
            profile = data.get("profileInfo", {})
            social = data.get("socialInfo", {})

            theme_color = discord.Color.from_rgb(88, 101, 242)

            # --- Embed 1: Basic Info
            embed_basic = discord.Embed(
                title=f"💎 Player — {basic.get('nickname', 'Unknown')}",
                description=f"🔗 **JOIN : [JOIN NOW](https://discord.gg/RXSh8MpsZA)**",
                color=theme_color,
                timestamp=datetime.now()
            )
            embed_basic.set_thumbnail(url=ctx.author.display_avatar.url)
            embed_basic.add_field(name="👤 Developer", value="**TANVIR**", inline=False)
            embed_basic.add_field(
                name="Account Basic Info",
                value="\n".join([
                    f"**• UID:** `{uid}`",
                    f"**• Level:** {basic.get('level', '?')} (Exp: {basic.get('exp', '?')})",
                    f"**• Region:** {basic.get('region', 'Unknown')}",
                    f"**• Likes:** {basic.get('liked', '0')}",
                    f"**• Honor Score:** {credit.get('creditScore', 'N/A')}",
                    f"**• Signature:** {social.get('signature', 'None') or 'None'}"
                ]),
                inline=False
            )

            # --- Embed 2: Rank & Activity
            embed_rank = discord.Embed(title="🎮 Rank & Activity", color=theme_color)
            embed_rank.add_field(
                name="Account Stats",
                value="\n".join([
                    f"**• BR Rank Points:** {basic.get('rankingPoints', '?')}",
                    f"**• CS Rank Points:** {basic.get('csRankingPoints', '?')}",
                    f"**• Badges:** {basic.get('badgeCnt', '0')}",
                    f"**• Created:** {self.convert_unix_timestamp(basic.get('createAt', 0))}",
                    f"**• Last Login:** {self.convert_unix_timestamp(basic.get('lastLoginAt', 0))}"
                ]),
                inline=False
            )

            # --- Embed 3: Profile & Pet
            embed_profile = discord.Embed(title="🧥 Profile & Pet", color=theme_color)
            embed_profile.add_field(
                name="Profile Info",
                value="\n".join([
                    f"**• Avatar ID:** {profile.get('avatarId', 'N/A')}",
                    f"**• Banner ID:** {basic.get('bannerId', 'N/A')}",
                    f"**• Equipped Skills:** {profile.get('equipedSkills', 'N/A')}",
                ]),
                inline=False
            )
            embed_profile.add_field(
                name="Pet Info",
                value="\n".join([
                    f"**• Pet Name:** {pet.get('name', 'N/A')}",
                    f"**• Level:** {pet.get('level', 'N/A')} (Exp: {pet.get('exp', 'N/A')})",
                    f"**• Equipped:** {'Yes' if pet.get('isSelected') else 'No'}"
                ]),
                inline=False
            )

            # --- Embed 4: Clan & Captain
            embed_clan = discord.Embed(title="🛡️ Clan & Captain", color=theme_color)
            if clan:
                embed_clan.add_field(
                    name="Guild Info",
                    value="\n".join([
                        f"**• Guild Name:** {clan.get('clanName', 'N/A')}",
                        f"**• Guild ID:** `{clan.get('clanId', 'N/A')}`",
                        f"**• Level:** {clan.get('clanLevel', 'N/A')}",
                        f"**• Members:** {clan.get('memberNum', '?')}/{clan.get('capacity', '?')}"
                    ]),
                    inline=False
                )
            if captain:
                embed_clan.add_field(
                    name="Leader Info",
                    value="\n".join([
                        f"**• Name:** {captain.get('nickname', 'N/A')}",
                        f"**• UID:** `{captain.get('accountId', 'N/A')}`",
                        f"**• Level:** {captain.get('level', 'N/A')}",
                        f"**• Rank Points:** {captain.get('rankingPoints', 'N/A')}",
                        f"**• Badges:** {captain.get('badgeCnt', 'N/A')}"
                    ]),
                    inline=False
                )

            # --- Embed 5: Profile Card & Outfit
            embed_image = discord.Embed(title="🖼️ Profile Card", color=theme_color)
            embed_image.set_image(url=f"https://profile.thug4ff.com/api/profile_card?uid={uid}")

            embeds = [embed_basic, embed_rank, embed_profile, embed_clan, embed_image]

            # outfit image
            outfit_filename = f"outfit_{uid}.png"
            outfit_buf = None
            try:
                async with self.session.get(f"{self.generate_url}?uid={uid}") as imgr:
                    if imgr.status == 200:
                        outfit_bytes = await imgr.read()
                        outfit_buf = io.BytesIO(outfit_bytes)
                        embed_outfit = discord.Embed(title="🧾 Outfit Image", color=theme_color)
                        embed_outfit.set_image(url=f"attachment://{outfit_filename}")
                        embeds.append(embed_outfit)
            except Exception as e:
                print("Outfit fetch error:", e)

            if outfit_buf:
                outfit_buf.seek(0)
                discord_file = discord.File(fp=outfit_buf, filename=outfit_filename)
                await ctx.send(embeds=embeds, file=discord_file)
            else:
                await ctx.send(embeds=embeds)

        except Exception as e:
            await ctx.send(f"❌ Unexpected error: `{e}`")
        finally:
            gc.collect()

    async def _send_player_not_found(self, ctx, uid):
        embed = discord.Embed(
            title="❌ Player Not Found",
            description=f"UID `{uid}` not found or inaccessible.",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)

    async def _send_api_error(self, ctx):
        embed = discord.Embed(
            title="⚠️ API Error",
            description="The Free Fire API is not responding. Try again later.",
            color=discord.Color.orange()
        )
        await ctx.send(embed=embed)

    async def cog_unload(self):
        await self.session.close()


async def setup(bot):
    await bot.add_cog(InfoCommands(bot))
