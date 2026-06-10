"""
Discord Keyword Monitor Bot
============================
Monitors a source channel for trigger keywords.
When detected, unlocks a target channel for @everyone,
and simultaneously disables sending messages for @everyone
in the Appy applications channel (so only the Appy bot can post there).

Supports both regular text channels (#) and announcement channels (📢)
as the SOURCE_CHANNEL_ID.

Requirements:
    pip install discord.py

Setup:
    1. Enable "Message Content Intent" in the Discord Developer Portal
       (Bot > Privileged Gateway Intents > Message Content Intent)
    2. Fill in the config variables below.
    3. Run: python discord_keyword_bot.py
"""

import discord
from discord import app_commands
from discord.ext import commands
import os

# ─────────────────────────────────────────────
#  CONFIGURATION  ← edit these values
# ─────────────────────────────────────────────
BOT_TOKEN = os.getenv("DISCORD_TOKEN")

# ID of the channel the bot watches for keywords
# Can be a regular text channel (#) or an announcement channel (📢)
SOURCE_CHANNEL_ID = os.getenv("SOURCE_CHANNEL")

# ID of the channel that gets unlocked when a keyword is detected
TARGET_CHANNEL_ID = os.getenv("TARGET_CHANNEL")

# Keywords that trigger the unlock (case-insensitive)
KEYWORDS = ["Moderator Applications Are Open!"]

# ID of the Appy applications channel (moderator/staff applications, etc.)
# When a keyword unlock fires, @everyone will have send_messages DENIED here
# so only the Appy bot can post — preventing members from spamming it.
APPLICATIONS_CHANNEL_ID = os.getenv("APPLICATIONS_CHANNEL")

# ID of the channel where the bot sends the unlock confirmation message
ANNOUNCEMENT_CHANNEL_ID = os.getenv("ANNOUNCEMENT_CHANNEL")
# ─────────────────────────────────────────────


# ── Bot activity toggle ───────────────────────
# When False the bot is effectively deaf — on_message will silently ignore
# all messages and no channel unlocking will occur until re-enabled.
bot_active = True


# ── Intents ──────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree


SUPPORTED_CHANNEL_TYPES = (
    discord.ChannelType.text,
    discord.ChannelType.news,
)


# ── Startup ───────────────────────────────────
@bot.event
async def on_ready():
    await tree.sync()
    print(f"✅  Logged in as {bot.user} (ID: {bot.user.id})")
    print(f"👁  Watching channel      : {SOURCE_CHANNEL_ID}")
    print(f"🔓  Will unlock channel   : {TARGET_CHANNEL_ID}")
    print(f"📋  Applications channel  : {APPLICATIONS_CHANNEL_ID}")
    print(f"📢  Announcement channel  : {ANNOUNCEMENT_CHANNEL_ID}")
    print(f"🔑  Keywords              : {KEYWORDS}")
    print(f"⚡  Bot active            : {bot_active}")


# ── Message listener ──────────────────────────
@bot.event
async def on_message(message: discord.Message):
    # 1. Never respond to our own messages
    if message.author == bot.user:
        return

    # 2. If the bot is disabled, ignore everything silently
    if not bot_active:
        return

    # 3. Only handle text and announcement channels
    if message.channel.type not in SUPPORTED_CHANNEL_TYPES:
        return

    # 4. Only act on messages in the designated source channel
    if message.channel.id != SOURCE_CHANNEL_ID:
        await bot.process_commands(message)
        return

    # 5. Check for keywords (case-insensitive, whitespace-normalised)
    content_lower = message.content.lower()
    triggered_by = next((kw for kw in KEYWORDS if kw.lower() in ' '.join(content_lower.split())), None)

    if triggered_by:
        print(f'🔑 Keyword "{triggered_by}" detected from {message.author} — unlocking channel.')
        await unlock_channel(message.guild, message.channel)
    else:
        print(f"⏭ No keyword matched. Content was: {content_lower!r}")

    await bot.process_commands(message)


# ── Core helper ───────────────────────────────
async def unlock_channel(
    guild: discord.Guild,
    trigger_channel: discord.TextChannel,
) -> None:
    """
    Three things happen when a keyword is detected:

      1. TARGET_CHANNEL_ID is unlocked — @everyone gets view_channel and
         send_messages set to True so members can read and chat there.

      2. APPLICATIONS_CHANNEL_ID is muted — @everyone has send_messages
         set to False so only the Appy bot can post in the applications
         channel, keeping it clean and spam-free.

      3. A confirmation message is sent to ANNOUNCEMENT_CHANNEL_ID so the
         unlock is announced in a specific channel rather than the source.

    How Discord permission overrides work
    ──────────────────────────────────────
    Every channel can store a list of PermissionOverwrite objects,
    one per role or member.  Each overwrite has three states per
    permission flag:

        True  → explicitly ALLOW  (green checkmark in the UI)
        False → explicitly DENY   (red  X      in the UI)
        None  → inherit from role / server defaults

    guild.default_role is the @everyone role — it applies to all
    members who don't have a more specific role override.

    set_permissions() merges the kwargs you pass into that role's
    existing overwrite, leaving all unspecified flags unchanged.
    """

    everyone = guild.default_role

    # ── Step 1: Unlock the target channel ────────────────────────────────
    target = guild.get_channel(TARGET_CHANNEL_ID)

    if target is None:
        await trigger_channel.send(
            f"⚠️ Could not find target channel (ID `{TARGET_CHANNEL_ID}`). Check the config."
        )
        return

    await target.set_permissions(
        everyone,
        view_channel=True,
        send_messages=True,
        reason=f"Keyword unlock triggered in #{trigger_channel.name}",
    )

    # ── Step 2: Mute the Appy applications channel ───────────────────────
    apps_channel = guild.get_channel(APPLICATIONS_CHANNEL_ID)

    if apps_channel is None:
        await trigger_channel.send(
            f"⚠️ Could not find applications channel (ID `{APPLICATIONS_CHANNEL_ID}`). "
            "Check the config. The target channel was still unlocked."
        )
    else:
        await apps_channel.set_permissions(
            everyone,
            view_channel=True,
            send_messages=False,
            reason=f"Applications channel muted during keyword unlock in #{trigger_channel.name}",
        )

    # ── Step 3: Send confirmation to the announcement channel ────────────
    announcement_channel = guild.get_channel(ANNOUNCEMENT_CHANNEL_ID)
    apps_mention = apps_channel.mention if apps_channel else f"`{APPLICATIONS_CHANNEL_ID}`"

    if announcement_channel is None:
        await trigger_channel.send(
            f"⚠️ Could not find announcement channel (ID `{ANNOUNCEMENT_CHANNEL_ID}`). Check the config."
        )
    else:
        await announcement_channel.send(
            f"🔓 **{target.mention} has been unlocked!** Everyone can now read and send messages there.\n"
            f"📋 **{apps_mention}** has been muted for `@everyone` — only Appy can post there now."
        )


# ── Slash Commands ────────────────────────────

@tree.command(name="toggle", description="Enable or disable the bot's keyword monitoring.")
@app_commands.describe(state="True to enable the bot, False to disable it.")
@app_commands.checks.has_permissions(manage_guild=True)
async def toggle(interaction: discord.Interaction, state: bool):
    """
    Flips the global bot_active flag.
    - True  → bot resumes watching for keywords and unlocking channels
    - False → bot ignores all messages until re-enabled
    Restricted to members with the Manage Server permission.
    """
    global bot_active
    bot_active = state

    if bot_active:
        print(f"⚡ Bot enabled by {interaction.user}")
        await interaction.response.send_message(
            "✅ Bot is now **enabled** — listening for keywords and ready to unlock channels.",
            ephemeral=True,
        )
    else:
        print(f"⛔ Bot disabled by {interaction.user}")
        await interaction.response.send_message(
            "⛔ Bot is now **disabled** — all keyword monitoring has been paused.",
            ephemeral=True,
        )


@toggle.error
async def toggle_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message(
            "❌ You need the **Manage Server** permission to use this command.",
            ephemeral=True,
        )


@tree.command(name="status", description="Show the bot's current configuration.")
async def status(interaction: discord.Interaction):
    embed = discord.Embed(title="🤖 Keyword Bot Status", color=discord.Color.blurple())
    embed.add_field(name="Source Channel",       value=f"<#{SOURCE_CHANNEL_ID}>",       inline=False)
    embed.add_field(name="Target Channel",       value=f"<#{TARGET_CHANNEL_ID}>",       inline=False)
    embed.add_field(name="Applications Channel", value=f"<#{APPLICATIONS_CHANNEL_ID}>", inline=False)
    embed.add_field(name="Announcement Channel", value=f"<#{ANNOUNCEMENT_CHANNEL_ID}>", inline=False)
    embed.add_field(name="Keywords",             value=", ".join(f"`{k}`" for k in KEYWORDS), inline=False)
    embed.add_field(name="Bot Active",           value="✅ Enabled" if bot_active else "⛔ Disabled", inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)


@tree.command(name="lock", description="Lock the target channel again (deny @everyone).")
@app_commands.checks.has_permissions(manage_channels=True)
async def lock(interaction: discord.Interaction):
    guild  = interaction.guild
    target = guild.get_channel(TARGET_CHANNEL_ID)

    if target is None:
        await interaction.response.send_message(
            f"⚠️ Target channel ID `{TARGET_CHANNEL_ID}` not found.", ephemeral=True
        )
        return

    everyone = guild.default_role

    await target.set_permissions(
        everyone,
        view_channel=False,
        send_messages=False,
        reason=f"Manual lock by {interaction.user}",
    )

    await interaction.response.send_message(
        f"🔒 **{target.mention}** has been locked. `@everyone` can no longer read or send messages.",
        ephemeral=True,
    )


@lock.error
async def lock_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message(
            "❌ You need the **Manage Channels** permission to use this command.",
            ephemeral=True,
        )


@tree.command(name="unlock", description="Manually unlock the target channel for @everyone.")
@app_commands.checks.has_permissions(manage_channels=True)
async def unlock(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    await unlock_channel(interaction.guild, interaction.channel)
    await interaction.followup.send("✅ Done.", ephemeral=True)


# ── Entry point ───────────────────────────────
if __name__ == "__main__":
    bot.run(BOT_TOKEN)
