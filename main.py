import discord
from discord.ext import commands
import json
import os
from datetime import datetime, timedelta, timezone
import re
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

# ==================== CONFIG ====================
TOKEN = os.environ["DISCORD_BOT_TOKEN"]
PREFIX = "+"
LOG_CHANNEL_ID = 1544449119454634035

SPECIAL_USERS = [
    "1517924890370375928",
]

# +ban +unban only
BAN_COMMAND_USERS = [
    "1517924890370375928",
    "1391635894045380619",
]

# +kick only
KICK_COMMAND_USERS = [
    "1517924890370375928",
]

# +bl +unbl only
BL_COMMAND_USERS = [
    "1517924890370375928",
]

# Exact role names from your server (used once to find role IDs).
# After the bot finds them, it saves the ROLE IDs — so if you rename a role,
# permissions still work without updating this list.
ROLES = {
    # Perm level -> role IDs (primary) + optional names (display / fallback only)
    1: {
        "ids": [1540435355633975366],  # Test Moderator
        "names": ["Test Moderator", "Test Mod", "[ TM ] • Test Mod"],
    },
    2: {
        "ids": [1512494871158591779],  # Moderator
        "names": ["Moderator", "[ S ] • Moderator"],
    },
    3: {
        "ids": [
            1540434933166776400,  # Senior Mod
            1543926509520293908,  # Head Staff
        ],
        "names": ["Senior Mod", "Head Staff", "[ S ] • Senior Mod", "[ H ] • Head Staff"],
    },
    4: {
        "ids": [
            1512494871171043540,  # Admin
            1512494871171043541,  # Manager
            1543925240705585284,  # Overlord
            1534637036542365787,  # King
        ],
        "names": ["Admin", "ADMIN", "Manager", "Server-Manager", "Overlord", "King", "[ A ] • ADMIN", "[ SM ] • Server-Manager", "[ OV ] • Overlord"],
    },
    5: {
        "ids": [
            1540425618620162139,  # Founder
            1512494871171043543,  # Owners
            1544803993480466563,  # Co owners
        ],
        "names": ["FOUNDER", "Founder", "Owners", "Co - Owner", "Co-Owner", "Co owners", "[ F ] • FOUNDER", "[ O ] • Owners", "[ CO ] • Co - Owner"],
    },
}

BLACKLISTED_WORDS = [
    # slurs / hate
    "nigger", "nigga", "faggot", "fag", "tranny", "retard", "retarded",
    "nazi", "hitler", "kike", "chink", "spic", "coon", "beaner",
    # sexual / crude
    "femboy", "d*ck", "dick", "cock", "pussy", "whore", "slut", "hoe",
    "porn", "nudes", "onlyfans",
    # self-harm / threats
    "kys", "kill yourself", "kill urself", "hang yourself", "go die",
    "neck yourself", "end yourself",
]

# Scam / nitro bait — separate message + sanction reason "link"
SCAM_WORDS = [
    "free nitro", "discord.gift", "steamcommunity.com/gift",
    "free nitro giveaway", "nitro gift", "claim nitro",
]

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True
intents.moderation = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None)

# ==================== DATA ====================
os.makedirs("data", exist_ok=True)
SANCTIONS_FILE = "data/sanctions.json"
BLACKLIST_FILE = "data/blacklist.json"
SNIPE_FILE = "data/snipe.json"
ROLE_PERMS_FILE = "data/role_perms.json"  # saves role IDs so renames don't break perms

def load_json(path, default):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

sanctions_data = load_json(SANCTIONS_FILE, {})
blacklist = load_json(BLACKLIST_FILE, [])
snipe_data = load_json(SNIPE_FILE, {})
role_perms = load_json(ROLE_PERMS_FILE, {})  # {guild_id: {"1": [role_id, ...], ...}}

def save_sanctions(): save_json(SANCTIONS_FILE, sanctions_data)
def save_blacklist(): save_json(BLACKLIST_FILE, blacklist)
def save_snipe(): save_json(SNIPE_FILE, snipe_data)
def save_role_perms(): save_json(ROLE_PERMS_FILE, role_perms)

# ==================== HELPERS ====================
def _match_role_exact(guild: discord.Guild, name: str):
    """Match a role by exact name only (case-insensitive). No substring matching."""
    name = name.strip()
    if not name:
        return None
    role = discord.utils.find(lambda r, n=name: r.name == n, guild.roles)
    if role:
        return role
    role = discord.utils.find(lambda r, n=name: r.name.lower() == n.lower(), guild.roles)
    if role:
        return role
    if "•" in name:
        key = name.split("•")[-1].strip()
        role = discord.utils.find(lambda r, k=key: r.name.lower() == k.lower(), guild.roles)
        if role:
            return role
    return None

def resolve_role_ids(guild: discord.Guild, force: bool = False) -> dict:
    """
    Map perm levels -> set of role IDs.
    Prefer hardcoded IDs in ROLES (always correct).
    Names are only a fallback if an ID is missing from the guild.
    """
    gid = str(guild.id)
    # Hardcoded IDs always win unless force re-check from names for missing ones
    mapping = {}
    used_ids = set()
    for level in sorted(ROLES.keys(), reverse=True):
        entry = ROLES[level]
        found = []
        # New format: {"ids": [...], "names": [...]}
        if isinstance(entry, dict):
            for rid in entry.get("ids", []):
                if rid not in used_ids:
                    # Keep even if role missing (still in guild config)
                    found.append(rid)
                    used_ids.add(rid)
            # Name fallback only for IDs not already set
            for name in entry.get("names", []):
                role = _match_role_exact(guild, name)
                if role and role.id not in used_ids:
                    found.append(role.id)
                    used_ids.add(role.id)
        else:
            # Legacy list-of-names format
            for name in entry:
                role = _match_role_exact(guild, name)
                if role and role.id not in used_ids:
                    found.append(role.id)
                    used_ids.add(role.id)
        mapping[level] = found

    role_perms[gid] = {str(k): v for k, v in mapping.items()}
    save_role_perms()
    return {k: set(v) for k, v in mapping.items()}

def get_perm_level(member: discord.Member) -> int:
    if str(member.id) in SPECIAL_USERS:
        return 99
    if not member.guild:
        return 0
    cache = resolve_role_ids(member.guild)
    member_ids = {r.id for r in member.roles}
    highest = 0
    for level, role_ids in cache.items():
        if member_ids & role_ids:
            highest = max(highest, level)
    return highest

def has_perm(member: discord.Member, level: int) -> bool:
    return get_perm_level(member) >= level

def can_moderate(moderator: discord.Member, target: discord.Member) -> bool:
    if moderator.id == target.id:
        return False
    if moderator.id == moderator.guild.owner_id:
        return True
    if target.id == target.guild.owner_id:
        return False
    return moderator.top_role > target.top_role


async def send_log(embed: discord.Embed):
    """Send an embed to the configured log channel."""
    ch = bot.get_channel(LOG_CHANNEL_ID)
    if ch is None:
        try:
            ch = await bot.fetch_channel(LOG_CHANNEL_ID)
        except Exception:
            return
    try:
        await ch.send(embed=embed)
    except Exception:
        pass


def add_sanction(user_id: int, reason: str, mod_id: int):
    uid = str(user_id)
    if uid not in sanctions_data:
        sanctions_data[uid] = []
    entry = {
        "id": len(sanctions_data[uid]) + 1,
        "reason": reason,
        "date": datetime.now().strftime("%d/%m/%Y"),
        "moderator": str(mod_id)
    }
    sanctions_data[uid].append(entry)
    save_sanctions()
    return entry

async def get_target(ctx: commands.Context, arg: str = None):
    # 1) Explicit mentions first
    if ctx.message.mentions:
        return ctx.message.mentions[0]
    # 2) Reply target (use cached resolved message when available)
    if ctx.message.reference:
        ref = ctx.message.reference
        if ref.resolved and hasattr(ref.resolved, "author"):
            return ref.resolved.author
        if ref.message_id:
            try:
                msg = await ctx.channel.fetch_message(ref.message_id)
                return msg.author
            except Exception:
                pass
    # 3) Argument: ID or name
    if arg:
        arg = arg.strip()
        # Raw ID
        if arg.isdigit():
            try:
                return await bot.fetch_user(int(arg))
            except Exception:
                pass
        # Mention string <@id> / <@!id>
        if arg.startswith("<@") and arg.endswith(">"):
            raw = arg.replace("<@", "").replace("!", "").replace(">", "")
            if raw.isdigit():
                try:
                    return await bot.fetch_user(int(raw))
                except Exception:
                    pass
        # Name search in guild
        if ctx.guild:
            name = arg.lower()
            # exact match first
            for m in ctx.guild.members:
                if (
                    m.name.lower() == name
                    or (m.display_name and m.display_name.lower() == name)
                    or str(m).lower() == name
                ):
                    return m
            # partial match (starts with)
            for m in ctx.guild.members:
                if m.name.lower().startswith(name) or (m.display_name and m.display_name.lower().startswith(name)):
                    return m
    return None


async def get_member(guild: discord.Guild, user):
    """Get a Member from guild, trying cache then API fetch. Returns None if not in server."""
    if user is None or guild is None:
        return None
    uid = getattr(user, "id", user)
    try:
        uid = int(uid)
    except Exception:
        return None
    member = guild.get_member(uid)
    if member:
        return member
    try:
        return await guild.fetch_member(uid)
    except Exception:
        return None


async def empty_result(ctx, text: str):
    """Send a short 'nothing' message then delete both bot + user messages."""
    try:
        msg = await ctx.send(text)
    except Exception:
        msg = None
    try:
        await ctx.message.delete()
    except Exception:
        pass
    if msg:
        try:
            await msg.delete()
        except Exception:
            pass


SERVER_INVITE = "https://discord.gg/GtRfjpAjsA"

async def dm_unbanned(user):
    """Try to DM a user that they were unbanned. May fail if no mutual server / DMs closed."""
    if user is None or getattr(user, "bot", False):
        return False
    try:
        emb = discord.Embed(
            title="You have been unbanned",
            description=(
                "You have been **unbanned** from **Leo's empire**.\n\n"
                f"You can rejoin here: {SERVER_INVITE}"
            ),
            color=0x000000,
        )
        emb.set_footer(text="Leo's empire")
        await user.send(embed=emb)
        return True
    except Exception:
        # Fallback plain text
        try:
            await user.send(
                f"You have been unbanned from **Leo's empire**.\n"
                f"Rejoin here: {SERVER_INVITE}"
            )
            return True
        except Exception:
            return False

def parse_duration(text: str):
    match = re.match(r"^(\d+)([smhd])$", text.lower())
    if not match:
        return None
    num, unit = int(match.group(1)), match.group(2)
    if unit == "s": return timedelta(seconds=num)
    if unit == "m": return timedelta(minutes=num)
    if unit == "h": return timedelta(hours=num)
    if unit == "d": return timedelta(days=num)
    return None

# ==================== EVENTS ====================
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name="Leos empire"
        )
    )
    for guild in bot.guilds:
        try:
            resolve_role_ids(guild)
            print(f"Perm roles loaded for: {guild.name}")
        except Exception as e:
            print(f"Role resolve failed for {guild.name}: {e}")

@bot.event
async def on_message_delete(message):
    if message.author.bot or not message.guild:
        return
    # Ignore the +clear command itself so it never gets sniped
    if message.content and message.content.startswith(f"{PREFIX}clear"):
        return
    # Save text + image/attachments so +snipe can show them
    attachments = []
    image_url = None
    for att in message.attachments:
        attachments.append({"url": att.url, "filename": att.filename, "content_type": att.content_type or ""})
        if image_url is None and (
            (att.content_type and att.content_type.startswith("image/"))
            or att.filename.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"))
        ):
            image_url = att.url
    # Stickers (optional display as name)
    stickers = [s.name for s in getattr(message, "stickers", [])] if getattr(message, "stickers", None) else []
    content = message.content or ""
    if not content and not attachments and not stickers:
        content = "*no text*"
    elif not content and attachments:
        content = ""
    snipe_data[str(message.channel.id)] = {
        "content": content if content else "*attachment only*",
        "author": str(message.author),
        "author_id": message.author.id,
        "avatar": str(message.author.display_avatar.url),
        "time": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "image_url": image_url,
        "attachments": attachments,
        "stickers": stickers,
    }
    save_snipe()

@bot.event
async def on_bulk_message_delete(messages):
    # Bulk deletes (from +clear / purge) should not update snipe
    if not messages:
        return
    channel_id = str(messages[0].channel.id)
    if channel_id in snipe_data:
        del snipe_data[channel_id]
        save_snipe()

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # Mention reply
    if bot.user.mentioned_in(message) and not message.mention_everyone:
        content = message.content.replace(f"<@{bot.user.id}>", "").replace(f"<@!{bot.user.id}>", "").strip()
        if len(content) < 3:
            await message.channel.send(f"My prefix on this server is: `{PREFIX}`")
            return

    # Filter words (Perm 5 + Special Users are immune)
    content_lower = message.content.lower()
    member = message.guild.get_member(message.author.id) if message.guild else None
    immune = member and (has_perm(member, 5) or str(member.id) in SPECIAL_USERS)

    if not immune:
        # Scam / nitro bait → delete, ping, sanction as "link"
        for word in SCAM_WORDS:
            if word in content_lower:
                try:
                    await message.delete()
                except:
                    pass
                add_sanction(message.author.id, "link", bot.user.id)
                await message.channel.send(
                    f"{message.author.mention} this a some bad things you got going"
                )
                emb = discord.Embed(title="Scam / Link Filter", color=0x000000, timestamp=datetime.now())
                emb.add_field(name="User", value=f"{message.author} (`{message.author.id}`)")
                emb.add_field(name="Matched", value=word)
                emb.add_field(name="Message", value=f"```{message.content[:800]}```", inline=False)
                await send_log(emb)
                return

        # Normal blacklisted words → delete, ping, sanction as "bad word"
        for word in BLACKLISTED_WORDS:
            if word in content_lower:
                try:
                    await message.delete()
                except:
                    pass
                add_sanction(message.author.id, "bad word", bot.user.id)
                await message.channel.send(
                    f"{message.author.mention} you said a blacklisted word"
                )
                emb = discord.Embed(title="Blacklisted Word", color=0x000000, timestamp=datetime.now())
                emb.add_field(name="User", value=f"{message.author} (`{message.author.id}`)")
                emb.add_field(name="Word", value=word)
                emb.add_field(name="Message", value=f"```{message.content[:800]}```", inline=False)
                await send_log(emb)
                return

    await bot.process_commands(message)

@bot.event
async def on_member_join(member):
    if str(member.id) in blacklist:
        try:
            await member.ban(reason="Blacklisted")
        except:
            pass

@bot.event
async def on_member_update(before: discord.Member, after: discord.Member):
    """Log manual (and any) timeouts into sanctions so +sanctions shows them."""
    try:
        before_to = before.timed_out_until
        after_to = after.timed_out_until
    except Exception:
        return

    # Timeout applied or extended
    if after_to is not None and before_to != after_to:
        # Skip if this bot just did +tempmute (already logged there)
        mod_id = bot.user.id if bot.user else 0
        reason = "timeout"
        try:
            async for entry in after.guild.audit_logs(limit=6, action=discord.AuditLogAction.member_update):
                if entry.target and entry.target.id == after.id:
                    # recent enough (within 20s)
                    if (datetime.now(timezone.utc) - entry.created_at).total_seconds() < 20:
                        if entry.user:
                            mod_id = entry.user.id
                        if entry.reason:
                            reason = entry.reason
                        break
        except Exception:
            pass

        # If the bot applied it, +tempmute already added a sanction
        if bot.user and mod_id == bot.user.id:
            return

        # Format remaining duration
        try:
            now = datetime.now(timezone.utc)
            until = after_to if after_to.tzinfo else after_to.replace(tzinfo=timezone.utc)
            secs = max(0, int((until - now).total_seconds()))
            if secs >= 86400:
                dur = f"{secs // 86400}d"
            elif secs >= 3600:
                dur = f"{secs // 3600}h"
            elif secs >= 60:
                dur = f"{secs // 60}m"
            else:
                dur = f"{secs}s"
        except Exception:
            dur = "?"

        text = f"timeout {dur}"
        if reason and reason != "timeout":
            text = f"timeout {dur} - {reason}"
        add_sanction(after.id, text, mod_id)

        log = discord.Embed(title="Timeout (manual/other)", color=0x000000, timestamp=datetime.now())
        log.add_field(name="User", value=f"{after} (`{after.id}`)", inline=False)
        log.add_field(name="Moderator", value=f"<@{mod_id}> (`{mod_id}`)", inline=False)
        log.add_field(name="Duration", value=dur, inline=True)
        log.add_field(name="Reason", value=reason, inline=True)
        await send_log(log)

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("Missing permissions.")
    else:
        try:
            await ctx.send(f"Error: `{error}`")
        except:
            pass

# ==================== COMMANDS ====================
@bot.command()
async def ping(ctx):
    await ctx.send(f"Pong! `{round(bot.latency*1000)}ms`")

@bot.command()
async def perms(ctx):
    cache = resolve_role_ids(ctx.guild)
    emb = discord.Embed(title="Permissions", color=0x000000)
    for level in sorted(ROLES.keys()):
        mentions = []
        seen = set()
        # Show every configured role ID for this level
        for rid in cache.get(level, set()):
            if rid in seen:
                continue
            seen.add(rid)
            role = ctx.guild.get_role(rid)
            if role:
                mentions.append(role.mention)
            else:
                mentions.append(f"`{rid}`")
        # Also try name fallback for any configured names not already shown
        entry = ROLES.get(level, {})
        names = entry.get("names", []) if isinstance(entry, dict) else []
        for name in names:
            role = discord.utils.find(
                lambda r, n=name: r.name == n or r.name.lower() == n.lower(),
                ctx.guild.roles
            )
            if role and role.id not in seen:
                seen.add(role.id)
                mentions.append(role.mention)
        value = "\n".join(mentions) if mentions else "None found"
        if level == 5:
            value += "\n\n**Has access to all commands**"
        emb.add_field(name=f"Perm {level}", value=value, inline=False)
    emb.set_footer(text="Role IDs are saved — renaming a role will not break perms. Use +syncroles to rescan names.")
    await ctx.send(embed=emb)

@bot.command()
async def syncroles(ctx):
    """Re-scan role names and update saved role IDs (Perm 5 / special only)."""
    if not has_perm(ctx.author, 5) and str(ctx.author.id) not in SPECIAL_USERS:
        return
    cache = resolve_role_ids(ctx.guild, force=True)
    lines = []
    for level in sorted(cache.keys()):
        roles = []
        for rid in cache[level]:
            role = ctx.guild.get_role(rid)
            roles.append(role.mention if role else f"`{rid}`")
        lines.append(f"**Perm {level}:** {' '.join(roles) if roles else 'none'}")
    emb = discord.Embed(
        title="Roles synced",
        description="\n".join(lines) or "No roles matched.",
        color=0x000000
    )
    emb.set_footer(text="Saved role IDs. Renaming these roles will still keep the same perms.")
    await ctx.send(embed=emb)

@bot.command()
async def snipe(ctx):
    data = snipe_data.get(str(ctx.channel.id))
    if not data:
        return await empty_result(ctx, "Nothing to snipe.")
    desc = data.get("content") or ""
    if data.get("stickers"):
        desc = (desc + "\n" if desc and desc != "*attachment only*" else "") + "Sticker: " + ", ".join(data["stickers"])
    if not desc:
        desc = "*attachment only*"
    emb = discord.Embed(title="Snipe", description=desc, color=0x000000)
    emb.add_field(name="Author", value=data["author"], inline=True)
    deleted_text = data.get("time", "unknown")
    if data.get("timestamp"):
        try:
            ts = datetime.fromisoformat(data["timestamp"])
            deleted_text = discord.utils.format_dt(ts, "R")
        except:
            pass
    emb.add_field(name="Deleted", value=deleted_text, inline=True)
    # Show deleted image in the embed
    if data.get("image_url"):
        emb.set_image(url=data["image_url"])
    # Non-image attachments as links
    other = []
    for att in data.get("attachments") or []:
        is_img = (att.get("content_type") or "").startswith("image/") or att.get("filename", "").lower().endswith(
            (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")
        )
        if not is_img and att.get("url"):
            other.append(f"[{att.get('filename', 'file')}]({att['url']})")
    if other:
        emb.add_field(name="Files", value="\n".join(other[:5]), inline=False)
    emb.set_footer(text="Crow Bots")
    await ctx.send(embed=emb)

@bot.command(aliases=["warns"])
async def sanctions(ctx, target: str = None):
    try:
        user = await get_target(ctx, target)
        if user is None:
            user = ctx.author
        lst = sanctions_data.get(str(user.id), [])
        if not lst:
            return await empty_result(ctx, f"**{user}** has no sanctions.")
        text = "\n".join(f"{s['id']} - {s['date']}: {s['reason']}" for s in lst)
        # Discord embed description limit is 4096
        if len(text) > 4000:
            text = text[:4000] + "\n..."
        emb = discord.Embed(description=text, color=0x000000)
        avatar = getattr(getattr(user, "display_avatar", None), "url", None)
        emb.set_author(name=str(user), icon_url=avatar)
        emb.set_footer(text="Crow Bots")
        await ctx.send(embed=emb)
    except Exception as e:
        await ctx.send(f"Failed to load sanctions: `{e}`")

@bot.command(name="del")
async def del_sanction(ctx, action: str = None, arg1: str = None, arg2: str = None):
    if action != "sanction":
        return
    if not has_perm(ctx.author, 2):
        return

    user = None
    number = None

    # User from mention or reply
    if ctx.message.mentions:
        user = ctx.message.mentions[0]
    elif ctx.message.reference:
        user = await get_target(ctx, None)

    # Parse args:
    # +del sanction 1              (reply/mention provides user, arg1 = number)
    # +del sanction @user 1        (arg1 = user, arg2 = number)
    # +del sanction 123456789 1    (arg1 = id, arg2 = number)
    if arg1 and arg1.isdigit() and arg2 is None:
        number = arg1
    elif arg1 is not None and arg2 is not None and arg2.isdigit():
        if user is None:
            user = await get_target(ctx, arg1)
        number = arg2
    elif arg1 is not None and not arg1.isdigit() and arg2 is not None and arg2.isdigit():
        if user is None:
            user = await get_target(ctx, arg1)
        number = arg2

    if not user or not number or not str(number).isdigit():
        return await ctx.send("Usage: `+del sanction @user <number>` or reply + `+del sanction <number>`")

    uid = str(user.id)
    num = int(number)
    if uid not in sanctions_data or not any(s["id"] == num for s in sanctions_data[uid]):
        return await ctx.send("Sanction not found.")
    deleted = next(s for s in sanctions_data[uid] if s["id"] == num)
    sanctions_data[uid] = [s for s in sanctions_data[uid] if s["id"] != num]
    for i, s in enumerate(sanctions_data[uid], 1):
        s["id"] = i
    save_sanctions()
    await ctx.send(f"Sanction deleted: {deleted['date']}: {deleted['reason']}")
    log = discord.Embed(title="Del Sanction", color=0x000000, timestamp=datetime.now())
    log.add_field(name="User", value=f"{user} (`{user.id}`)", inline=False)
    log.add_field(name="Moderator", value=f"{ctx.author} (`{ctx.author.id}`)", inline=False)
    log.add_field(name="Deleted", value=f"{deleted['date']}: {deleted['reason']}", inline=False)
    await send_log(log)

@bot.command()
async def warn(ctx, *, args: str = None):
    if not has_perm(ctx.author, 1):
        return

    user = None
    reason = "No reason provided"

    if ctx.message.mentions:
        user = ctx.message.mentions[0]
        if args:
            reason = args
            for m in ctx.message.mentions:
                reason = reason.replace(f"<@{m.id}>", "").replace(f"<@!{m.id}>", "")
            reason = reason.strip() or "No reason provided"
    elif ctx.message.reference:
        user = await get_target(ctx, None)
        if args:
            reason = args.strip()
    elif args:
        parts = args.split(None, 1)
        user = await get_target(ctx, parts[0])
        if user and len(parts) > 1:
            reason = parts[1]
        elif not user:
            return await ctx.send("Usage: `+warn @user [reason]` or reply + reason")

    if not user:
        return await ctx.send("Usage: `+warn @user [reason]` or reply + reason")

    add_sanction(user.id, reason, ctx.author.id)
    emb = discord.Embed(title="warn", description=f"{user.mention} was warned\nreason: {reason}", color=0x000000)
    await ctx.send(embed=emb)
    log = discord.Embed(title="Warn", color=0x000000, timestamp=datetime.now())
    log.add_field(name="User", value=f"{user} (`{user.id}`)", inline=False)
    log.add_field(name="Moderator", value=f"{ctx.author} (`{ctx.author.id}`)", inline=False)
    log.add_field(name="Reason", value=reason, inline=False)
    await send_log(log)

@bot.command()
async def clearwarns(ctx, target: str = None):
    if not has_perm(ctx.author, 3):
        return
    user = await get_target(ctx, target)
    if not user:
        return await ctx.send("Usage: `+clearwarns @user` or reply")
    sanctions_data[str(user.id)] = []
    save_sanctions()
    await ctx.send(f"Cleared all sanctions for **{user}**")
    log = discord.Embed(title="Clear Warns", color=0x000000, timestamp=datetime.now())
    log.add_field(name="User", value=f"{user} (`{user.id}`)", inline=False)
    log.add_field(name="Moderator", value=f"{ctx.author} (`{ctx.author.id}`)", inline=False)
    await send_log(log)

@bot.command()
async def tempmute(ctx, *, args: str = None):
    if not has_perm(ctx.author, 1):
        return
    if not args:
        return await ctx.send("Usage: `+tempmute @user <duration> [reason]` or reply + `<duration> [reason]`")

    user = None
    duration = None
    reason = "No reason"

    if ctx.message.mentions:
        user = ctx.message.mentions[0]
        rest = args
        for m in ctx.message.mentions:
            rest = rest.replace(f"<@{m.id}>", "").replace(f"<@!{m.id}>", "")
        rest = rest.strip()
        parts = rest.split(None, 1)
        duration = parts[0] if parts else None
        if len(parts) > 1:
            reason = parts[1]
    elif ctx.message.reference:
        user = await get_target(ctx, None)
        parts = args.strip().split(None, 1)
        duration = parts[0] if parts else None
        if len(parts) > 1:
            reason = parts[1]
    else:
        parts = args.split(None, 2)
        if not parts:
            return await ctx.send("Usage: `+tempmute @user <duration> [reason]` or reply + `<duration> [reason]`")
        user = await get_target(ctx, parts[0])
        duration = parts[1] if len(parts) > 1 else None
        reason = parts[2] if len(parts) > 2 else "No reason"

    if not user or not duration:
        return await ctx.send("Usage: `+tempmute @user <duration> [reason]` or reply + `<duration> [reason]`")

    member = await get_member(ctx.guild, user)
    if not member:
        return await ctx.send("User not in server.")
    if member.id == ctx.author.id:
        return await ctx.send("You can't mute yourself.")

    delta = parse_duration(duration)
    if not delta:
        return await ctx.send("Invalid duration (examples: `30s` `10m` `1h` `7d`)")
    # Discord max timeout is 28 days
    if delta.total_seconds() > 28 * 86400:
        return await ctx.send("Max timeout is 28 days.")

    try:
        await member.timeout(delta, reason=reason)
        add_sanction(user.id, f"timeout {duration} - {reason}", ctx.author.id)
        await ctx.send(f"Successfully timed out {member.mention} {duration} for the following reason: `{reason}`")
        log = discord.Embed(title="Tempmute", color=0x000000, timestamp=datetime.now())
        log.add_field(name="User", value=f"{member} (`{member.id}`)", inline=False)
        log.add_field(name="Moderator", value=f"{ctx.author} (`{ctx.author.id}`)", inline=False)
        log.add_field(name="Duration", value=duration, inline=True)
        log.add_field(name="Reason", value=reason, inline=True)
        await send_log(log)
    except discord.Forbidden:
        await ctx.send("Missing permissions: move my role **above** the target's role and enable **Timeout Members** for me.")
    except Exception as e:
        await ctx.send(f"Failed: {e}")

@bot.command()
async def unmute(ctx, target: str = None):
    if not has_perm(ctx.author, 1):
        return
    user = await get_target(ctx, target)
    if not user:
        return await ctx.send("Usage: `+unmute @user` or reply")
    member = await get_member(ctx.guild, user)
    if not member:
        return await ctx.send("User not in server.")
    try:
        await member.timeout(None)
        await ctx.send(f"Unmuted {member.mention} successfully")
        log = discord.Embed(title="Unmute", color=0x000000, timestamp=datetime.now())
        log.add_field(name="User", value=f"{member} (`{member.id}`)", inline=False)
        log.add_field(name="Moderator", value=f"{ctx.author} (`{ctx.author.id}`)", inline=False)
        await send_log(log)
    except Exception as e:
        await ctx.send(f"Failed to unmute: {e}")

@bot.command()
async def mutelist(ctx):
    if not has_perm(ctx.author, 1):
        return
    muted = [m for m in ctx.guild.members if m.is_timed_out() and m.timed_out_until]
    if not muted:
        return await empty_result(ctx, "There are no muted members.")

    # Sort by longest remaining timeout first
    muted.sort(key=lambda m: m.timed_out_until, reverse=True)

    def format_remaining(until):
        now = datetime.now(timezone.utc)
        if until.tzinfo is None:
            until = until.replace(tzinfo=timezone.utc)
        delta = until - now
        if delta.total_seconds() <= 0:
            return "0.0 days 0.0 hours and 0.0 minutes"
        total_seconds = int(delta.total_seconds())
        days = total_seconds // 86400
        hours = (total_seconds % 86400) // 3600
        minutes = (total_seconds % 3600) // 60
        return f"{days}.0 days {hours}.0 hours and {minutes}.0 minutes"

    lines = []
    # Discord embed description limit ~4096 chars; keep a safe number of lines
    max_show = 40
    for m in muted[:max_show]:
        remaining = format_remaining(m.timed_out_until)
        lines.append(f"{m.mention} : {remaining}")

    description = "**Timeouts**\n" + "\n".join(lines)
    not_shown = len(muted) - max_show
    if not_shown > 0:
        description += f"\n{not_shown} not showed"

    emb = discord.Embed(
        title="Current mutes",
        description=description,
        color=0x000000
    )
    await ctx.send(embed=emb)

@bot.command()
async def ban(ctx, *, args: str = None):
    if str(ctx.author.id) not in BAN_COMMAND_USERS:
        return

    user = None
    reason = "No reason"

    if ctx.message.mentions:
        user = ctx.message.mentions[0]
        if args:
            reason = args
            for m in ctx.message.mentions:
                reason = reason.replace(f"<@{m.id}>", "").replace(f"<@!{m.id}>", "")
            reason = reason.strip() or "No reason"
    elif ctx.message.reference:
        user = await get_target(ctx, None)
        if args:
            reason = args.strip()
    elif args:
        parts = args.split(None, 1)
        user = await get_target(ctx, parts[0])
        if user and len(parts) > 1:
            reason = parts[1]

    if not user:
        return await ctx.send("Usage: `+ban @user [reason]` or reply + reason")
    if user.id == ctx.author.id:
        return await ctx.send("You can't ban yourself.")
    try:
        await ctx.guild.ban(user, reason=reason)
        await ctx.send(f"Banned **{user}** | Reason: {reason}")
        log = discord.Embed(title="Ban", color=0x000000, timestamp=datetime.now())
        log.add_field(name="User", value=f"{user} (`{user.id}`)", inline=False)
        log.add_field(name="Moderator", value=f"{ctx.author} (`{ctx.author.id}`)", inline=False)
        log.add_field(name="Reason", value=reason, inline=False)
        await send_log(log)
    except Exception as e:
        await ctx.send(f"Failed: {e}")

@bot.command()
async def unban(ctx, user_id: str = None):
    if str(ctx.author.id) not in BAN_COMMAND_USERS:
        return
    if not user_id:
        return await ctx.send("Usage: `+unban <user id>`")
    try:
        user = await bot.fetch_user(int(user_id))
        await ctx.guild.unban(user)
        dm_ok = await dm_unbanned(user)
        extra = " (DM sent)" if dm_ok else " (could not DM — no mutual server or DMs closed)"
        await ctx.send(f"Unbanned **{user}**{extra}")
        log = discord.Embed(title="Unban", color=0x000000, timestamp=datetime.now())
        log.add_field(name="User", value=f"{user} (`{user.id}`)", inline=False)
        log.add_field(name="Moderator", value=f"{ctx.author} (`{ctx.author.id}`)", inline=False)
        log.add_field(name="DM", value="Sent" if dm_ok else "Failed", inline=True)
        await send_log(log)
    except Exception as e:
        await ctx.send(f"Failed to unban: {e}")

@bot.command()
async def kick(ctx, *, args: str = None):
    if str(ctx.author.id) not in KICK_COMMAND_USERS:
        return

    user = None
    reason = "No reason"

    if ctx.message.mentions:
        user = ctx.message.mentions[0]
        if args:
            reason = args
            for m in ctx.message.mentions:
                reason = reason.replace(f"<@{m.id}>", "").replace(f"<@!{m.id}>", "")
            reason = reason.strip() or "No reason"
    elif ctx.message.reference:
        user = await get_target(ctx, None)
        if args:
            reason = args.strip()
    elif args:
        parts = args.split(None, 1)
        user = await get_target(ctx, parts[0])
        if user and len(parts) > 1:
            reason = parts[1]

    if not user:
        return await ctx.send("Usage: `+kick @user [reason]` or reply + reason")
    if user.id == ctx.author.id:
        return await ctx.send("You can't kick yourself.")
    member = await get_member(ctx.guild, user)
    if not member:
        return await ctx.send("User not in server.")
    try:
        await member.kick(reason=reason)
        await ctx.send(f"Kicked **{user}** | Reason: {reason}")
        log = discord.Embed(title="Kick", color=0x000000, timestamp=datetime.now())
        log.add_field(name="User", value=f"{user} (`{user.id}`)", inline=False)
        log.add_field(name="Moderator", value=f"{ctx.author} (`{ctx.author.id}`)", inline=False)
        log.add_field(name="Reason", value=reason, inline=False)
        await send_log(log)
    except Exception as e:
        await ctx.send(f"Failed: {e}")

@bot.command()
async def clear(ctx, *args):
    """
    +clear [amount]              – delete last N messages (default 10, max 100)
    +clear @user [amount]        – delete that user's messages (scans recent history)
    +clear <user_id> [amount]    – same, works even if they left the server
    Reply + +clear [amount]      – target the replied user

    Discord only allows bulk-delete of messages newer than 14 days.
    When a user is targeted, the bot scans further back (up to ~1000 msgs)
    and removes only their messages within that window.
    """
    if not has_perm(ctx.author, 4):
        return

    amount = 10
    target = None

    # 1) Mentions
    if ctx.message.mentions:
        target = ctx.message.mentions[0]
        for a in reversed(args):
            if str(a).isdigit():
                amount = int(a)
                break
    # 2) Reply
    elif ctx.message.reference:
        target = await get_target(ctx, None)
        if args and str(args[0]).isdigit():
            amount = int(args[0])
    # 3) Args: amount only, or user_id [amount]
    elif args:
        if len(args) == 1 and str(args[0]).isdigit():
            num = int(args[0])
            if num > 10_000_000_000_000_000:  # likely a user ID
                try:
                    target = await bot.fetch_user(num)
                    amount = 100
                except Exception:
                    amount = max(1, min(num, 100))
            else:
                amount = max(1, min(num, 100))
        else:
            try:
                target = await get_target(ctx, args[0])
            except Exception:
                target = None
            if target is None and str(args[0]).isdigit():
                try:
                    target = await bot.fetch_user(int(args[0]))
                except Exception:
                    pass
            if len(args) > 1 and str(args[1]).isdigit():
                amount = int(args[1])
            elif target:
                amount = 100

    if target:
        amount = max(1, min(amount, 1000))
    else:
        amount = max(1, min(amount, 100))

    def check(m):
        if target is None:
            return True
        return m.author.id == target.id

    try:
        await ctx.message.delete()
    except Exception:
        pass

    try:
        deleted = await ctx.channel.purge(limit=amount, check=check)
        if target and deleted:
            try:
                feedback = await ctx.send(f"Cleared **{len(deleted)}** message(s) from **{target}**.")
                await feedback.delete(delay=3)
            except Exception:
                pass
    except Exception as e:
        try:
            await ctx.send(f"Failed to clear: `{e}`")
        except Exception:
            pass

    # Don't let +clear messages be sniped
    channel_id = str(ctx.channel.id)
    if channel_id in snipe_data:
        del snipe_data[channel_id]
        save_snipe()

def find_role(guild, role_query: str):
    """Find a role by ID, mention, exact name, or partial name (e.g. 'manager' -> Manager)."""
    if not role_query:
        return None
    q = role_query.strip()
    # Mention <@&id>
    if q.startswith("<@&") and q.endswith(">"):
        rid = q[3:-1]
        if rid.isdigit():
            return guild.get_role(int(rid))
    # By ID
    if q.isdigit():
        role = guild.get_role(int(q))
        if role:
            return role
    q_lower = q.lower()
    # Exact name (case-insensitive)
    role = discord.utils.find(lambda r: r.name.lower() == q_lower, guild.roles)
    if role:
        return role
    # Starts with query (e.g. "head" -> "Head Staff")
    starts = [r for r in guild.roles if r.name.lower().startswith(q_lower) and r.name != "@everyone"]
    if len(starts) == 1:
        return starts[0]
    if len(starts) > 1:
        # Prefer shortest name
        starts.sort(key=lambda r: len(r.name))
        return starts[0]
    # Contains query (e.g. "manager" in "Server-Manager", "staff" in "Head Staff")
    contains = [r for r in guild.roles if q_lower in r.name.lower() and r.name != "@everyone"]
    if len(contains) == 1:
        return contains[0]
    if len(contains) > 1:
        # Prefer shortest name so "mod" prefers "Moderator" over longer names when possible
        contains.sort(key=lambda r: (len(r.name), r.name.lower()))
        return contains[0]
    return None

@bot.command()
async def addrole(ctx, *, args: str = None):
    if not has_perm(ctx.author, 3):
        return
    if not args:
        return await ctx.send("Usage: `+addrole @user RoleName` or reply + `RoleName`")

    user = None
    role_name = None

    # Mention = target user; everything else is the role name
    if ctx.message.mentions:
        user = ctx.message.mentions[0]
        role_name = args
        for m in ctx.message.mentions:
            role_name = role_name.replace(f"<@{m.id}>", "").replace(f"<@!{m.id}>", "")
        role_name = role_name.strip()
    # Real Discord reply (not just a quote)
    elif ctx.message.reference:
        user = await get_target(ctx, None)
        role_name = args.strip()
    else:
        parts = args.split(None, 1)
        # +addrole <user_id> <role name...>
        if len(parts) >= 1 and parts[0].isdigit() and ctx.guild and ctx.guild.get_member(int(parts[0])):
            user = await get_target(ctx, parts[0])
            role_name = parts[1] if len(parts) > 1 else None
        # +addrole <role_id only>  → role id applied to self
        elif len(parts) == 1 and parts[0].isdigit() and find_role(ctx.guild, parts[0]):
            user = ctx.author
            role_name = parts[0]
        else:
            user = ctx.author
            role_name = args.strip()

    if not user or not role_name:
        return await ctx.send("Usage: `+addrole @user RoleName` or reply + `RoleName`")

    member = await get_member(ctx.guild, user)
    if not member:
        return await ctx.send("User not in server.")

    role = find_role(ctx.guild, role_name)
    if not role:
        return await ctx.send("Role not found.")
    if role >= ctx.author.top_role and ctx.author.id != ctx.guild.owner_id:
        return await ctx.send("You can't give a role that is higher or equal to your highest role.")
    if role >= ctx.guild.me.top_role:
        return await ctx.send("I can't assign that role because it is higher or equal to my highest role.")
    if role in member.roles:
        return await ctx.send(f"{member.mention} already has the {role.mention} role.")
    try:
        await member.add_roles(role)
        await ctx.send("1 role was added to 1 member")
    except Exception as e:
        await ctx.send(f"Failed: {e}")

@bot.command()
async def delrole(ctx, *, args: str = None):
    if not has_perm(ctx.author, 3):
        return
    if not args:
        return await ctx.send("Usage: `+delrole @user RoleName` or reply + `RoleName`")

    user = None
    role_name = None

    if ctx.message.mentions:
        user = ctx.message.mentions[0]
        role_name = args
        for m in ctx.message.mentions:
            role_name = role_name.replace(f"<@{m.id}>", "").replace(f"<@!{m.id}>", "")
        role_name = role_name.strip()
    elif ctx.message.reference:
        user = await get_target(ctx, None)
        role_name = args.strip()
    else:
        parts = args.split(None, 1)
        if len(parts) >= 1 and parts[0].isdigit() and ctx.guild and ctx.guild.get_member(int(parts[0])):
            user = await get_target(ctx, parts[0])
            role_name = parts[1] if len(parts) > 1 else None
        elif len(parts) == 1 and parts[0].isdigit() and find_role(ctx.guild, parts[0]):
            user = ctx.author
            role_name = parts[0]
        else:
            user = ctx.author
            role_name = args.strip()

    if not user or not role_name:
        return await ctx.send("Usage: `+delrole @user RoleName` or reply + `RoleName`")

    member = await get_member(ctx.guild, user)
    if not member:
        return await ctx.send("User not in server.")

    role = find_role(ctx.guild, role_name)
    if not role:
        return await ctx.send("Role not found.")
    if role >= ctx.author.top_role and ctx.author.id != ctx.guild.owner_id:
        return await ctx.send("You can't remove a role that is higher or equal to your highest role.")
    if role >= ctx.guild.me.top_role:
        return await ctx.send("I can't remove that role because it is higher or equal to my highest role.")
    if role not in member.roles:
        return await ctx.send(f"{member.mention} does not have the {role.mention} role.")
    try:
        await member.remove_roles(role)
        await ctx.send("1 rôle was successfully removed from 1 member")
    except Exception as e:
        await ctx.send(f"Failed: {e}")

@bot.command()
async def derank(ctx, target: str = None):
    if not has_perm(ctx.author, 3):
        return
    user = await get_target(ctx, target)
    if not user:
        return await ctx.send("Usage: `+derank @user` or reply")
    if user.id == ctx.author.id:
        return await ctx.send("You can't derank yourself.")
    member = await get_member(ctx.guild, user)
    if not member:
        return await ctx.send("User not in server.")
    try:
        roles = [r for r in member.roles if r != ctx.guild.default_role and not r.managed]
        await member.remove_roles(*roles)
        await ctx.send(f"{member.mention} was deranked successfully")
    except Exception as e:
        await ctx.send(f"Failed: {e}")

@bot.command()
async def create(ctx, emoji: str = None, *, name: str = None):
    if not has_perm(ctx.author, 4):
        return
    # Support both +create <name> and +create <emoji> <name>
    if emoji and not name:
        name = emoji
        emoji = None
    if not name:
        return await ctx.send("Usage: `+create [emoji] <name>`")
    role_name = f"{emoji} {name}".strip() if emoji else name.strip()
    existing = discord.utils.find(lambda r: r.name.lower() == role_name.lower(), ctx.guild.roles)
    if existing:
        return await ctx.send(f"A role named **{role_name}** already exists.")
    try:
        new_role = await ctx.guild.create_role(name=role_name, reason=f"Created by {ctx.author}")
        await ctx.send(f"Successfully created role **{new_role.name}**")
    except discord.Forbidden:
        await ctx.send("I don't have permission to create roles.")
    except Exception as e:
        await ctx.send(f"Failed: {e}")

@bot.command()
async def rolemembers(ctx, *, role_query: str = None):
    if not has_perm(ctx.author, 2):
        return
    if not role_query:
        return await ctx.send("Usage: `+rolemembers <role>`")
    role = discord.utils.find(
        lambda r: r.name.lower() == role_query.lower() or str(r.id) == role_query,
        ctx.guild.roles
    )
    if not role:
        return await ctx.send("Role not found.")
    members = role.members
    if not members:
        return await ctx.send(f"No members have the role **{role.name}**.")
    lines = [f"{m.mention} (`{m.id}`)" for m in members[:30]]
    emb = discord.Embed(
        title=f"Members with {role.name} ({len(members)})",
        description="\n".join(lines),
        color=0x000000
    )
    if len(members) > 30:
        emb.set_footer(text=f"Showing 30/{len(members)}")
    await ctx.send(embed=emb)

@bot.command()
async def bl(ctx, target: str = None, *, reason: str = "No reason"):
    if str(ctx.author.id) not in BL_COMMAND_USERS:
        return
    user = await get_target(ctx, target)
    if not user:
        return await ctx.send("Usage: `+bl @user [reason]` or reply")
    if user.id == ctx.author.id:
        return await ctx.send("You can't blacklist yourself.")
    member = ctx.guild.get_member(user.id)
    if ctx.message.reference and target and not target.isdigit() and not ctx.message.mentions:
        reason = f"{target} {reason}".strip()
    uid = str(user.id)
    if uid not in blacklist:
        blacklist.append(uid)
        save_blacklist()
    try:
        await ctx.guild.ban(user, reason=f"Blacklisted: {reason}")
    except:
        pass
    emb = discord.Embed(title="blacklist", description=f"{user.mention} banned and blacklisted\nreason: {reason}", color=0x000000)
    await ctx.send(embed=emb)
    log = discord.Embed(title="Blacklist", color=0x000000, timestamp=datetime.now())
    log.add_field(name="User", value=f"{user} (`{user.id}`)", inline=False)
    log.add_field(name="Moderator", value=f"{ctx.author} (`{ctx.author.id}`)", inline=False)
    log.add_field(name="Reason", value=reason, inline=False)
    await send_log(log)

@bot.command()
async def unbl(ctx, user_id: str = None):
    if str(ctx.author.id) not in BL_COMMAND_USERS:
        return
    if not user_id:
        return await ctx.send("Usage: `+unbl <user id>`")
    uid = user_id.strip()
    if uid in blacklist:
        blacklist.remove(uid)
        save_blacklist()
    user = None
    try:
        user = await bot.fetch_user(int(uid))
        try:
            await ctx.guild.unban(user)
        except Exception:
            pass
        dm_ok = await dm_unbanned(user)
        extra = " (DM sent)" if dm_ok else " (could not DM — no mutual server or DMs closed)"
        await ctx.send(f"Removed `{uid}` from blacklist and unbanned.{extra}")
        log = discord.Embed(title="Unblacklist", color=0x000000, timestamp=datetime.now())
        log.add_field(name="User", value=f"{user} (`{user.id}`)", inline=False)
        log.add_field(name="Moderator", value=f"{ctx.author} (`{ctx.author.id}`)", inline=False)
        log.add_field(name="DM", value="Sent" if dm_ok else "Failed", inline=True)
        await send_log(log)
    except Exception:
        await ctx.send(f"Removed `{uid}` from blacklist.")

@bot.command()
async def userinfo(ctx, target: str = None):
    user = await get_target(ctx, target) or ctx.author
    member = ctx.guild.get_member(user.id)
    emb = discord.Embed(color=0x000000)
    emb.set_author(name=str(user), icon_url=user.display_avatar.url)
    emb.set_thumbnail(url=user.display_avatar.url)
    emb.add_field(name="ID", value=user.id, inline=True)
    emb.add_field(name="Created", value=discord.utils.format_dt(user.created_at, "R"), inline=True)
    if member:
        emb.add_field(name="Joined", value=discord.utils.format_dt(member.joined_at, "R"), inline=True)
    await ctx.send(embed=emb)

@bot.command()
async def serverinfo(ctx):
    g = ctx.guild
    emb = discord.Embed(title=g.name, color=0x000000)
    if g.icon:
        emb.set_thumbnail(url=g.icon.url)
    emb.add_field(name="Owner", value=f"<@{g.owner_id}>", inline=True)
    emb.add_field(name="Members", value=g.member_count, inline=True)
    emb.add_field(name="Created", value=discord.utils.format_dt(g.created_at, "R"), inline=True)
    await ctx.send(embed=emb)

@bot.command()
async def help(ctx):
    emb = discord.Embed(
        title="Command List",
        color=0x000000,
        description=(
            "Prefix: `+`\n"
            "You can **reply** to a message instead of mentioning the user.\n\n"
            "**Bot maker:** teix · **Founder:** LEO"
        )
    )
    emb.add_field(
        name="Perm 1",
        value="`+help` `+warn <member> [reason]` `+mutelist` `+perms` `+sanctions <member>` `+tempmute <member> <duration> [reason]` `+unmute <member>`",
        inline=False
    )
    emb.add_field(
        name="Perm 2",
        value="`+del sanction <member> <number>` `+rolemembers <role>`",
        inline=False
    )
    emb.add_field(
        name="Perm 3",
        value="`+derank <member>` `+clearwarns <member>` `+addrole <member> <role>` `+delrole <member> <role>`",
        inline=False
    )
    emb.add_field(
        name="Perm 4",
        value="`+clear [number] [member]` `+create [emoji] [name]`",
        inline=False
    )
    emb.add_field(
        name="Perm 5",
        value="**Has access to all commands**",
        inline=False
    )
    emb.add_field(
        name="Special Users only",
        value="`+ban` `+unban` `+kick` `+bl` `+unbl` (user ID only)",
        inline=False
    )
    emb.add_field(
        name="Everyone",
        value="`+userinfo` `+serverinfo` `+snipe` `+ping`",
        inline=False
    )
    emb.set_footer(text="Bot maker: teix • Founder: LEO")
    await ctx.send(embed=emb)

# ==================== KEEP-ALIVE (for hosts that sleep) ====================
class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Bot is online")

    def log_message(self, format, *args):
        return  # silence request logs


def start_keep_alive():
    """Tiny HTTP server so uptime monitors can ping the bot and keep the process awake."""
    port = int(os.environ.get("PORT", 8080))
    try:
        server = HTTPServer(("0.0.0.0", port), _HealthHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        print(f"Keep-alive server running on port {port}")
    except Exception as e:
        print(f"Keep-alive server failed to start: {e}")


# ==================== RUN ====================
start_keep_alive()
bot.run(TOKEN)
