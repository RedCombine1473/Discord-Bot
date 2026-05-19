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

# ─────────────────────────────────────────────
#  CONFIGURATION  ← edit these values
# ─────────────────────────────────────────────
BOT_TOKEN        = "your bot token"

# ID of the channel the bot watches for keywords
# Can be a regular text channel (#) or an announcement channel (📢)
SOURCE_CHANNEL_ID = 1506019449680171148

# ID of the channel that gets unlocked when a keyword is detected
TARGET_CHANNEL_ID = 1506020282060767262

# Keywords that trigger the unlock (case-insensitive)
KEYWORDS = ["Moderator Applications"]

# ID of the Appy applications channel (moderator/staff applications, etc.)
# When a keyword unlock fires, @everyone will have send_messages DENIED here
# so only the Appy bot can post — preventing members from spamming it.
APPLICATIONS_CHANNEL_ID = 111122223333444455
# ─────────────────────────────────────────────


# ── Intents ──────────────────────────────────
# message_content=True is a Privileged Intent.
# Without it, on_message won't see message text.
intents = discord.Intents.default()
intents.message_content = True          # required to read message content
intents.guilds = True                   # required to manage channels / roles

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree                         # shorthand for the slash-command tree

# Channel types that on_message should act on.
# discord.ChannelType.news is Discord's internal name for announcement (📢) channels.
SUPPORTED_CHANNEL_TYPES = (
    discord.ChannelType.text,   # regular # text channel
    discord.ChannelType.news,   # announcement 📢 channel
)


# ── Startup ───────────────────────────────────
@bot.event
async def on_ready():
    """Fires once when the bot has connected and is ready."""
    await tree.sync()                   # register slash commands with Discord
    print(f"✅  Logged in as {bot.user} (ID: {bot.user.id})")
    print(f"👁  Watching channel      : {SOURCE_CHANNEL_ID}")
    print(f"🔓  Will unlock channel   : {TARGET_CHANNEL_ID}")
    print(f"📋  Applications channel  : {APPLICATIONS_CHANNEL_ID}")
    print(f"🔑  Keywords              : {KEYWORDS}")


# ── Message listener ──────────────────────────
@bot.event
async def on_message(message: discord.Message):
    """
    Called for every message the bot can see.

    Flow:
      1. Ignore messages from the bot itself.
      2. Ignore messages from unsupported channel types (e.g. DMs, forums).
      3. Ignore messages not in SOURCE_CHANNEL_ID.
      4. Check whether any keyword appears in the message (case-insensitive).
      5. If a match is found, call unlock_channel().
    """

    print(f"📨 Message received | Author: {message.author} | Channel ID: {message.channel.id} | Type: {message.channel.type} | Content: {message.content!r}")

    # 1. Never respond to our own messages (prevents infinite loops)
    if message.author == bot.user:
        print("⏭ Skipped: own message")
        return

    # 2. Only handle text and announcement (📢) channels.
    #    discord.ChannelType.news is Discord's name for announcement channels.
    #    Without this check, DMs or forum posts could cause unexpected behaviour.
    if message.channel.type not in SUPPORTED_CHANNEL_TYPES:
        print(f"⏭ Skipped: unsupported channel type ({message.channel.type})")
        return

    # 3. Only act on messages in the designated source channel
    if message.channel.id != SOURCE_CHANNEL_ID:
        print(f"⏭ Skipped: wrong channel ({message.channel.id} != {SOURCE_CHANNEL_ID})")
        await bot.process_commands(message)
        return

    # 4. Check for keywords (case-insensitive substring match)
    content_lower = message.content.lower()
    triggered_by = next((kw for kw in KEYWORDS if kw.lower() in ' '.join(content_lower.split())), None)

    if triggered_by:
        print(f'🔑 Keyword "{triggered_by}" detected — unlocking channel.')
        await unlock_channel(message.guild, message.channel)
    else:
        print(f"⏭ No keyword matched. Content was: {content_lower!r}")

    # Allow prefix commands to work even inside the source channel
    await bot.process_commands(message)


# ── Core helper ───────────────────────────────
async def unlock_channel(
    guild: discord.Guild,
    trigger_channel: discord.TextChannel,
) -> None:
    """
    Two things happen atomically when a keyword is detected:

      1. TARGET_CHANNEL_ID is unlocked — @everyone gets view_channel and
         send_messages set to True so members can read and chat there.

      2. APPLICATIONS_CHANNEL_ID is muted — @everyone has send_messages
         set to False so only the Appy bot can post in the applications
         channel, keeping it clean and spam-free.

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

    everyone = guild.default_role   # the @everyone role

    # ── Step 1: Unlock the target channel ────────────────────────────────
    target = guild.get_channel(TARGET_CHANNEL_ID)

    if target is None:
        await trigger_channel.send(
            f"⚠️ Could not find target channel (ID `{TARGET_CHANNEL_ID}`). "
            "Check the config."
        )
        return

    # view_channel   = True  → @everyone can see the channel in the sidebar
    # send_messages  = True  → @everyone can type in the channel
    await target.set_permissions(
        everyone,
        view_channel=True,    # explicitly ALLOW reading
        send_messages=True,   # explicitly ALLOW sending
        reason=f"Keyword unlock triggered in #{trigger_channel.name}",
    )

    # ── Step 2: Mute the Appy applications channel ───────────────────────
    # We allow @everyone to still VIEW the channel (so they can read Appy's
    # prompts and see their application status), but DENY send_messages so
    # only Appy itself can post — preventing members from cluttering it.
    apps_channel = guild.get_channel(APPLICATIONS_CHANNEL_ID)

    if apps_channel is None:
        await trigger_channel.send(
            f"⚠️ Could not find applications channel (ID `{APPLICATIONS_CHANNEL_ID}`). "
            "Check the config. The target channel was still unlocked."
        )
    else:
        await apps_channel.set_permissions(
            everyone,
            view_channel=True,     # @everyone can still READ Appy's messages
            send_messages=False,   # explicitly DENY sending — Appy posts only
            reason=f"Applications channel muted during keyword unlock in #{trigger_channel.name}",
        )

    # ── Confirm in the source channel ────────────────────────────────────
    apps_mention = apps_channel.mention if apps_channel else f"`{APPLICATIONS_CHANNEL_ID}`"
    await trigger_channel.send(
        f"🔓 **{target.mention} has been unlocked!** Everyone can now read and send messages there.\n"
        f"📋 **{apps_mention}** has been muted for `@everyone` — only Appy can post there now."
    )


# ── Slash Commands ────────────────────────────

@tree.command(name="status", description="Show the bot's current configuration.")
async def status(interaction: discord.Interaction):
    """Returns the bot's current watch/target channel IDs and keyword list."""
    embed = discord.Embed(title="🤖 Keyword Bot Status", color=discord.Color.blurple())
    embed.add_field(name="Source Channel",       value=f"<#{SOURCE_CHANNEL_ID}>",       inline=False)
    embed.add_field(name="Target Channel",       value=f"<#{TARGET_CHANNEL_ID}>",       inline=False)
    embed.add_field(name="Applications Channel", value=f"<#{APPLICATIONS_CHANNEL_ID}>", inline=False)
    embed.add_field(name="Keywords",             value=", ".join(f"`{k}`" for k in KEYWORDS), inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)


@tree.command(name="lock", description="Lock the target channel again (deny @everyone).")
@app_commands.checks.has_permissions(manage_channels=True)
async def lock(interaction: discord.Interaction):
    """
    Manually re-locks the target channel.
    Restricted to members with the Manage Channels permission.
    """
    guild  = interaction.guild
    target = guild.get_channel(TARGET_CHANNEL_ID)

    if target is None:
        await interaction.response.send_message(
            f"⚠️ Target channel ID `{TARGET_CHANNEL_ID}` not found.", ephemeral=True
        )
        return

    everyone = guild.default_role

    # Set view_channel and send_messages to False (explicit DENY)
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
    """Handles missing-permissions errors for /lock."""
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message(
            "❌ You need the **Manage Channels** permission to use this command.",
            ephemeral=True,
        )


@tree.command(name="unlock", description="Manually unlock the target channel for @everyone.")
@app_commands.checks.has_permissions(manage_channels=True)
async def unlock(interaction: discord.Interaction):
    """
    Manually unlocks the target channel.
    Restricted to members with the Manage Channels permission.
    """
    await interaction.response.defer(ephemeral=True)
    await unlock_channel(interaction.guild, interaction.channel)
    await interaction.followup.send("✅ Done.", ephemeral=True)


# ── Entry point ───────────────────────────────
if __name__ == "__main__":
    bot.run(BOT_TOKEN)
