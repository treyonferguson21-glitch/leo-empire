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
APPEAL_CHANNEL_ID = 1544449118489808976  # unban appeals
MESSAGE_LOG_CHANNEL_ID = 1544449115881209917  # message delete / edit logs

# Panel theme (LEOS MM banner inspired — gold glow on dark)
THEME_COLOR = 0xFFCC00          # bright gold like the banner text
THEME_COLOR_DARK = 0x0A0A0A     # near-black for logs / secondary
FOOTER_TEXT = "LEOS MM • Bot by Mari"
BRAND_NAME = "LEOS MM"

# Welcome system
WELCOME_CHANNEL_ID = 1512494871644995740
WELCOME_CHAT_ID = 1512494872203100276
WELCOME_RULES_ID = 1512494871644995743
WELCOME_ANNOUNCEMENTS_ID = 1520525418858418236
WELCOME_INVITE_TRACKER_ID = 1520524185854804109

# Leave system
LEAVES_CHANNEL_ID = 1520523777258033353

# Boost thank-you system (Leo's Middleman)
BOOST_CHANNEL_ID = 1512494871838068862
BOOST_ROLE_ID = 1546910059014136022  # VIP role granted on boost

SPECIAL_USERS = [
    "1517924890370375928",
    "1391635894045380619",
]

# +ban +unban only
BAN_COMMAND_USERS = [
    "1517924890370375928",
    "1391635894045380619",
]

# +kick only
KICK_COMMAND_USERS = [
    "1517924890370375928",
    "1391635894045380619",
]

# +bl +unbl only
BL_COMMAND_USERS = [
    "1517924890370375928",
    "1391635894045380619",
]

# Extra roles that can use +addrole / +delrole only (NOT shown in +perms panel)
ROLE_MANAGE_EXTRA_IDS = [
    1547401287392301216,  # Head of Recruitment
]

# Exact role names from your server (used once to find role IDs).
# After the bot finds them, it saves the ROLE IDs — so if you rename a role,
# permissions still work without updating this list.
ROLES = {
    # Perm level -> role IDs (primary) + optional names (display / fallback only)
    # Higher level = higher staff. Higher staff can moderate lower staff.
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
            1512494871171043540,  # Administrator
            1512494871171043541,  # Manager
            1546192012435390515,  # Community Manager
            1548423059646578840,  # Staff Manager
            1545847662392119367,  # Head Manager
        ],
        "names": [
            "Administrator", "Admin", "ADMIN",
            "Manager", "Server-Manager",
            "Community Manager",
            "Staff Manager",
            "Head Manager",
            "[ A ] • ADMIN", "[ SM ] • Server-Manager", "[ OV ] • Overlord",
        ],
    },
    5: {
        "ids": [
            1534637036542365787,  # King
            1546912446004994108,  # Supervisor
            1544803993480466563,  # Co Owner
            1512494871171043543,  # Owners
        ],
        "names": [
            "King", "[ K ] • King",
            "Supervisor",
            "Co - Owner", "Co-Owner", "Co owners", "Co Owner", "[ CO ] • Co - Owner",
            "Owners", "[ O ] • Owners",
        ],
    },
    6: {
        "ids": [
            1540425618620162139,  # Founder
            1545842045258825809,  # Creator
        ],
        "names": [
            "FOUNDER", "Founder", "[ F ] • FOUNDER",
            "Creator", "[ C ] • Creator",
        ],
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

bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None, case_insensitive=True)

# ==================== DATA ====================
os.makedirs("data", exist_ok=True)
SANCTIONS_FILE = "data/sanctions.json"
BLACKLIST_FILE = "data/blacklist.json"
SNIPE_FILE = "data/snipe.json"
ROLE_PERMS_FILE = "data/role_perms.json"
TEMPROLES_FILE = "data/temproles.json"
COMMAND_PERMS_FILE = "data/command_perms.json"

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
clearing_channels = set()
role_perms = load_json(ROLE_PERMS_FILE, {})
temproles_data = load_json(TEMPROLES_FILE, [])
_temprole_tasks = {}
command_overrides = load_json(COMMAND_PERMS_FILE, {})

# Default required perm level per command (overridable via +changeperm)
DEFAULT_COMMAND_PERMS = {
    "warn": 1,
    "tempmute": 1,
    "unmute": 1,
    "mutelist": 1,
    "sanctions": 1,
    "perms": 1,
    "del": 2,  # del sanction
    "rolemembers": 2,
    "derank": 3,
    "clearwarns": 3,
    "addrole": 3,
    "delrole": 3,
    "clear": 4,
    "lock": 4,
    "unlock": 4,
    "create": 4,
    "temprole": 6,
    "syncroles": 6,
    "modstats": 6,
    "banlist": 5,
    "baninfo": 5,
    "changeperm": 6,
    "ban": 99,  # special users only (handled separately)
    "unban": 99,
    "kick": 99,
    "bl": 99,
    "unbl": 99,
}

def save_sanctions(): save_json(SANCTIONS_FILE, sanctions_data)
def save_blacklist(): save_json(BLACKLIST_FILE, blacklist)
def save_snipe(): save_json(SNIPE_FILE, snipe_data)
def save_role_perms(): save_json(ROLE_PERMS_FILE, role_perms)
def save_temproles(): save_json(TEMPROLES_FILE, temproles_data)
def save_command_perms(): save_json(COMMAND_PERMS_FILE, command_overrides)

def get_cmd_perm(name: str) -> int:
    key = name.lower().strip()
    if key in command_overrides:
        val = command_overrides[key]
        if val is None or str(val).lower() == "none":
            return 99  # effectively disabled / special only
        try:
            return int(val)
        except Exception:
            return DEFAULT_COMMAND_PERMS.get(key, 5)
    return DEFAULT_COMMAND_PERMS.get(key, 5)

# ==================== HELPERS ====================
def _match_role_exact(guild: discord.Guild, name: str):
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
    gid = str(guild.id)
    mapping = {}
    used_ids = set()
    for level in sorted(ROLES.keys(), reverse=True):
        entry = ROLES[level]
        found = []
        if isinstance(entry, dict):
            for rid in entry.get("ids", []):
                if rid not in used_ids:
                    found.append(rid)
                    used_ids.add(rid)
            for name in entry.get("names", []):
                role = _match_role_exact(guild, name)
                if role and role.id not in used_ids:
                    found.append(role.id)
                    used_ids.add(role.id)
        else:
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
    """Higher staff perm level can moderate lower staff — ignores Discord role position."""
    if moderator is None or target is None:
        return False
    if moderator.id == target.id:
        return False
    if str(moderator.id) in SPECIAL_USERS:
        return True
    if moderator.id == moderator.guild.owner_id:
        return True
    if target.id == target.guild.owner_id:
        return False
    if str(target.id) in SPECIAL_USERS:
        return False
    mod_level = get_perm_level(moderator)
    target_level = get_perm_level(target)
    # Regular members (no staff role) can always be moderated by staff
    if target_level == 0:
        return mod_level >= 1 or str(moderator.id) in SPECIAL_USERS
    # Staff targets: only strictly higher staff perm level (not Discord top_role)
    return mod_level > target_level

def has_role_manage_extra(member: discord.Member) -> bool:
    """True if member has a role in ROLE_MANAGE_EXTRA_IDS (addrole/delrole only)."""
    if not member or not getattr(member, "roles", None):
        return False
    extra = set(ROLE_MANAGE_EXTRA_IDS)
    return any(r.id in extra for r in member.roles)

# ==================== EVENTS ====================
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    await bot.change_presence(
        status=discord.Status.online,
        activity=discord.Streaming(
            name="LEOS MM",
            url="https://www.twitch.tv/discord"
        )
    )
    for guild in bot.guilds:
        try:
            resolve_role_ids(guild)
            print(f"Perm roles loaded for: {guild.name}")
        except Exception as e:
            print(f"Role resolve failed for {guild.name}: {e}")
    try:
        await restore_temproles()
        print(f"Temp roles restored: {len(temproles_data)} pending")
    except Exception as e:
        print(f"Temp role restore failed: {e}")

# ==================== EVENTS (all the rest) ====================
@bot.event
async def on_message_delete(message):
    if message.author.bot or not message.guild:
        return
    if message.channel.id in clearing_channels:
        return
    if message.content and message.content.startswith(f"{PREFIX}clear"):
        return
    attachments = []
    image_url = None
    IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".gifv")
    for att in message.attachments:
        # Prefer proxy_url — lasts longer after the message is deleted
        best_url = getattr(att, "proxy_url", None) or att.url
        attachments.append({
            "url": att.url,
            "proxy_url": getattr(att, "proxy_url", None) or att.url,
            "filename": att.filename,
            "content_type": att.content_type or "",
        })
        is_image = (
            (att.content_type and att.content_type.startswith("image/"))
            or att.filename.lower().endswith(IMAGE_EXTS)
        )
        if image_url is None and is_image:
            image_url = best_url
    # Also capture images from embeds (e.g. linked gifs / image embeds)
    if image_url is None:
        for emb in getattr(message, "embeds", []) or []:
            if emb.image and emb.image.url:
                image_url = emb.image.url
                break
            if emb.thumbnail and emb.thumbnail.url:
                image_url = emb.thumbnail.url
                break
            if emb.video and getattr(emb.video, "url", None):
                image_url = emb.video.url
                break
    stickers = [s.name for s in getattr(message, "stickers", [])] if getattr(message, "stickers", None) else []
    content = message.content or ""
    if not content and not attachments and not stickers and not image_url:
        content = "*no text*"
    elif not content and (attachments or image_url):
        content = ""
    snipe_data[str(message.channel.id)] = {
        "content": content if content else ("*attachment only*" if (attachments or image_url) else "*no text*"),
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

    # ---- Message log panel (delete) ----
    try:
        display_content = content if content else "*attachment only*"
        if stickers:
            display_content = (display_content + "\n" if display_content and display_content != "*attachment only*" else "") + "Sticker: " + ", ".join(stickers)
        display_content = censor_blacklisted(display_content) if display_content else "*no text*"
        if len(display_content) > 1000:
            display_content = display_content[:997] + "..."

        emb = discord.Embed(
            description=(
                f"**Message by** {message.author.mention} **deleted in** {message.channel.mention}\n\n"
                f"{display_content}"
            ),
            color=THEME_COLOR,
            timestamp=datetime.now(timezone.utc),
        )
        emb.set_author(
            name=str(message.author),
            icon_url=message.author.display_avatar.url,
        )
        emb.add_field(name="User ID", value=f"`{message.author.id}`", inline=True)
        emb.add_field(name="Channel", value=f"{message.channel.mention}", inline=True)
        if message.id:
            emb.add_field(name="Message ID", value=f"`{message.id}`", inline=True)
        if image_url:
            emb.set_image(url=image_url)
        other_files = []
        for att in attachments:
            is_img = (att.get("content_type") or "").startswith("image/") or att.get("filename", "").lower().endswith(
                (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".gifv")
            )
            link = att.get("proxy_url") or att.get("url")
            if not is_img and link:
                other_files.append(f"[{att.get('filename', 'file')}]({link})")
        if other_files:
            emb.add_field(name="Files", value="\n".join(other_files[:5]), inline=False)
        emb.set_footer(text=f"{BRAND_NAME} Logs • {datetime.now().strftime('%m/%d/%y, %I:%M %p')}")
        await send_message_log(emb)
    except Exception as e:
        print(f"Message delete log failed: {e}")

@bot.event
async def on_bulk_message_delete(messages):
    if not messages:
        return
    first = messages[0]
    if not first.guild:
        return
    # Skip if from clear command channel purge
    try:
        ch_id = first.channel.id if first.channel else None
        if ch_id and ch_id in clearing_channels:
            return
    except Exception:
        pass
    try:
        count = len(messages)
        channel = first.channel
        authors = {}
        for m in messages:
            if m.author and not m.author.bot:
                authors[m.author.id] = m.author
        author_list = ", ".join(f"{a.mention}" for a in list(authors.values())[:8])
        if len(authors) > 8:
            author_list += f" +{len(authors) - 8} more"
        emb = discord.Embed(
            description=(
                f"**Bulk delete** in {channel.mention if channel else '*unknown*'}\n\n"
                f"**{count}** message(s) removed"
                + (f"\nAuthors: {author_list}" if author_list else "")
            ),
            color=THEME_COLOR,
            timestamp=datetime.now(timezone.utc),
        )
        emb.set_author(name=f"{BRAND_NAME} Message Logs")
        emb.add_field(name="Count", value=f"`{count}`", inline=True)
        if channel:
            emb.add_field(name="Channel", value=channel.mention, inline=True)
        emb.set_footer(text=f"{BRAND_NAME} Logs • {datetime.now().strftime('%m/%d/%y, %I:%M %p')}")
        await send_message_log(emb)
    except Exception as e:
        print(f"Bulk delete log failed: {e}")

async def filter_bad_content(message) -> bool:
    if not message.guild or message.author.bot:
        return False
    content = message.content or ""
    if not content:
        return False
    content_lower = content.lower()
    member = message.guild.get_member(message.author.id)
    if member and has_perm(member, 5):
        return False

    async def _warn_and_cleanup(text: str):
        try:
            warn_msg = await message.channel.send(text)
        except Exception:
            return
        try:
            await warn_msg.delete(delay=3)
        except Exception:
            pass

    for word in SCAM_WORDS:
        if word in content_lower:
            try:
                await message.delete()
            except Exception:
                pass
            add_sanction(message.author.id, "link", bot.user.id if bot.user else 0)
            await _warn_and_cleanup(f"{message.author.mention} this a some bad things you got going")
            censored = censor_blacklisted(content[:800])
            emb = discord.Embed(
                title=f"✦ Scam / Link Filter — {BRAND_NAME}",
                color=THEME_COLOR,
                timestamp=datetime.now(timezone.utc),
            )
            emb.add_field(name="User", value=f"{message.author} (`{message.author.id}`)")
            emb.add_field(name="Matched", value="*(filtered link/scam)*")
            emb.add_field(name="Message", value=f"```{censored}```", inline=False)
            emb.set_footer(text=FOOTER_TEXT)
            await send_log(emb)
            return True

    for word in BLACKLISTED_WORDS:
        if word in content_lower:
            try:
                await message.delete()
            except Exception:
                pass
            add_sanction(message.author.id, "bad word", bot.user.id if bot.user else 0)
            await _warn_and_cleanup(f"{message.author.mention} you said a blacklisted word")
            # Censor the bad word so it doesn't show fully in staff logs
            censored_msg = censor_blacklisted(content[:800])
            censored_word = censor_blacklisted(word)
            emb = discord.Embed(
                title=f"✦ Blacklisted Word — {BRAND_NAME}",
                color=THEME_COLOR,
                timestamp=datetime.now(timezone.utc),
            )
            emb.add_field(name="User", value=f"{message.author} (`{message.author.id}`)")
            emb.add_field(name="Word", value=censored_word)
            emb.add_field(name="Message", value=f"```{censored_msg}```", inline=False)
            emb.set_footer(text=FOOTER_TEXT)
            await send_log(emb)
            return True

    return False

@bot.event
async def on_message(message):
    if message.author.bot:
        return
    if bot.user.mentioned_in(message) and not message.mention_everyone:
        content = message.content.replace(f"<@{bot.user.id}>", "").replace(f"<@!{bot.user.id}>", "").strip()
        if len(content) < 3:
            await message.channel.send(f"My prefix on this server is: `{PREFIX}`")
            return
    if await filter_bad_content(message):
        return
    if message.author.id in appeal_sessions:
        if await continue_appeal_session(message):
            return
    await bot.process_commands(message)

@bot.event
async def on_message_edit(before, after):
    if after.author.bot or not after.guild:
        return
    if (before.content or "") == (after.content or ""):
        return

    # ---- Message log panel (edit) ----
    try:
        before_text = before.content or "*empty*"
        after_text = after.content or "*empty*"
        if len(before_text) > 500:
            before_text = before_text[:497] + "..."
        if len(after_text) > 500:
            after_text = after_text[:497] + "..."
        before_text = censor_blacklisted(before_text)
        after_text = censor_blacklisted(after_text)

        emb = discord.Embed(
            description=(
                f"**Message by** {after.author.mention} **edited in** {after.channel.mention}\n\n"
                f"**Before:**\n{before_text}\n\n"
                f"**After:**\n{after_text}"
            ),
            color=THEME_COLOR,
            timestamp=datetime.now(timezone.utc),
        )
        emb.set_author(
            name=str(after.author),
            icon_url=after.author.display_avatar.url,
        )
        emb.add_field(name="User ID", value=f"`{after.author.id}`", inline=True)
        emb.add_field(name="Channel", value=after.channel.mention, inline=True)
        emb.add_field(name="Message ID", value=f"`{after.id}`", inline=True)
        if after.jump_url:
            emb.add_field(name="Jump", value=f"[Go to message]({after.jump_url})", inline=False)
        emb.set_footer(text=f"{BRAND_NAME} Logs • {datetime.now().strftime('%m/%d/%y, %I:%M %p')}")
        await send_message_log(emb)
    except Exception as e:
        print(f"Message edit log failed: {e}")

    await filter_bad_content(after)

@bot.event
async def on_member_join(member):
    if str(member.id) in blacklist:
        try:
            await member.ban(reason="Blacklisted")
        except Exception:
            pass
        return
    try:
        ch = bot.get_channel(WELCOME_CHANNEL_ID)
        if ch is None:
            ch = await bot.fetch_channel(WELCOME_CHANNEL_ID)
        count = member.guild.member_count or len(member.guild.members)
        emb = discord.Embed(
            title="New Member Joined!",
            description=(
                f"👏 Welcome {member.mention} to **{BRAND_NAME}**!\n\n"
                f"Glad to have you here. Check out our channels and enjoy your stay! 🎉"
            ),
            color=THEME_COLOR,
            timestamp=datetime.now(timezone.utc),
        )
        emb.add_field(
            name="Account Created",
            value=discord.utils.format_dt(member.created_at, "R"),
            inline=True,
        )
        emb.add_field(
            name="Member Count",
            value=f"#{count}",
            inline=True,
        )
        emb.set_thumbnail(url=member.display_avatar.url)
        emb.set_footer(text=FOOTER_TEXT)
        await ch.send(embed=emb)
    except Exception as e:
        print(f"Welcome message failed: {e}")

@bot.event
async def on_member_remove(member):
    try:
        ch = bot.get_channel(LEAVES_CHANNEL_ID)
        if ch is None:
            ch = await bot.fetch_channel(LEAVES_CHANNEL_ID)
        count = member.guild.member_count or len(member.guild.members)
        emb = discord.Embed(
            title="Member Left",
            description=(
                f"👋 **{member}** has left **{BRAND_NAME}**.\n\n"
                f"We'll miss you — hope to see you again soon!"
            ),
            color=THEME_COLOR,
            timestamp=datetime.now(timezone.utc),
        )
        emb.add_field(
            name="Account Created",
            value=discord.utils.format_dt(member.created_at, "R"),
            inline=True,
        )
        emb.add_field(
            name="Member Count",
            value=f"#{count}",
            inline=True,
        )
        if member.joined_at:
            emb.add_field(
                name="Joined",
                value=discord.utils.format_dt(member.joined_at, "R"),
                inline=True,
            )
        emb.set_thumbnail(url=member.display_avatar.url)
        emb.set_footer(text=FOOTER_TEXT)
        await ch.send(embed=emb)
    except Exception as e:
        print(f"Leave message failed: {e}")

@bot.event
async def on_member_update(before: discord.Member, after: discord.Member):
    # ---------- BOOST DETECTION (Leo's Middleman) ----------
    try:
        if before.premium_since is None and after.premium_since is not None:
            # User just boosted the server
            role = after.guild.get_role(BOOST_ROLE_ID)
            if role and role not in after.roles:
                try:
                    await after.add_roles(role, reason="Server boost reward — VIP")
                except Exception as e:
                    print(f"Failed to give boost role: {e}")

            # Build thank-you embed (LEOS MM themed)
            server_boosts = after.guild.premium_subscription_count or 0
            emb = discord.Embed(
                title=f"✦ Thank you for boosting! — {BRAND_NAME}",
                description=(
                    f"{after.mention} has boosted the server!\n\n"
                    f"As a reward, you've been granted the 💎 **VIP** role! 🎉\n\n"
                    f"Thank you for your support — it means everything to us!"
                ),
                color=THEME_COLOR,
                timestamp=datetime.now(timezone.utc),
            )
            emb.set_thumbnail(url=after.display_avatar.url)
            emb.add_field(name="🎁 Reward", value="💎 VIP", inline=True)
            emb.add_field(name="❤️ Their Boosts", value="1+", inline=True)
            emb.add_field(name="🖥️ Server Boosts", value=str(server_boosts), inline=True)
            emb.set_footer(text=FOOTER_TEXT)
            try:
                ch = bot.get_channel(BOOST_CHANNEL_ID)
                if ch is None:
                    ch = await bot.fetch_channel(BOOST_CHANNEL_ID)
                await ch.send(content=after.mention, embed=emb)
            except Exception as e:
                print(f"Boost thank-you message failed: {e}")
    except Exception as e:
        print(f"Boost check error: {e}")

    # ---------- TIMEOUT TRACKING (existing) ----------
    try:
        before_to = before.timed_out_until
        after_to = after.timed_out_until
    except Exception:
        return
    if after_to is not None and before_to != after_to:
        mod_id = bot.user.id if bot.user else 0
        reason = "timeout"
        try:
            async for entry in after.guild.audit_logs(limit=6, action=discord.AuditLogAction.member_update):
                if entry.target and entry.target.id == after.id:
                    if (datetime.now(timezone.utc) - entry.created_at).total_seconds() < 20:
                        if entry.user:
                            mod_id = entry.user.id
                        if entry.reason:
                            reason = entry.reason
                        break
        except Exception:
            pass
        if bot.user and mod_id == bot.user.id:
            return
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
        log = discord.Embed(
            title=f"✦ Timeout (manual/other) — {BRAND_NAME}",
            color=THEME_COLOR,
            timestamp=datetime.now(timezone.utc),
        )
        log.add_field(name="User", value=f"{after} (`{after.id}`)", inline=False)
        log.add_field(name="Moderator", value=f"<@{mod_id}> (`{mod_id}`)", inline=False)
        log.add_field(name="Duration", value=dur, inline=True)
        log.add_field(name="Reason", value=reason, inline=True)
        log.set_footer(text=FOOTER_TEXT)
        await send_log(log)

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    if isinstance(error, commands.MissingPermissions):
        return
    if isinstance(error, (commands.BadArgument, commands.MissingRequiredArgument, commands.TooManyArguments, commands.UserInputError)):
        name = ctx.command.name if ctx.command else "command"
        try:
            await ctx.send(f"invalid {name}")
        except Exception:
            pass
        return
    return

# ==================== COMMANDS ====================
@bot.command()
async def ping(ctx):
    emb = discord.Embed(
        title=f"✦ Pong — {BRAND_NAME}",
        description=f"Latency: **`{round(bot.latency*1000)}ms`**",
        color=THEME_COLOR,
        timestamp=datetime.now(timezone.utc),
    )
    emb.set_footer(text=FOOTER_TEXT)
    await ctx.send(embed=emb)

@bot.command()
async def perms(ctx):
    cache = resolve_role_ids(ctx.guild)
    emb = discord.Embed(
        title=f"✦ {BRAND_NAME} Permissions",
        description="Staff hierarchy & access levels\nRole IDs are saved — renaming a role will not break perms.",
        color=THEME_COLOR,
        timestamp=datetime.now(timezone.utc),
    )
    for level in sorted(ROLES.keys()):
        mentions = []
        seen = set()
        for rid in cache.get(level, set()):
            if rid in seen:
                continue
            role = ctx.guild.get_role(rid)
            if not role:
                continue
            seen.add(rid)
            mentions.append(role.mention)
        entry = ROLES.get(level, {})
        names = entry.get("names", []) if isinstance(entry, dict) else []
        for name in names:
            role = discord.utils.find(lambda r, n=name: r.name == n or r.name.lower() == n.lower(), ctx.guild.roles)
            if role and role.id not in seen:
                seen.add(role.id)
                mentions.append(role.mention)
        value = "\n".join(mentions) if mentions else "*None found*"
        if level == 6:
            value += "\n\n**Highest staff — advanced commands**"
        emb.add_field(name=f"▸ Perm {level}", value=value, inline=False)
    emb.set_footer(text=f"{FOOTER_TEXT}  •  Use +syncroles to rescan")
    await ctx.send(embed=emb)

@bot.command()
async def syncroles(ctx):
    if not has_perm(ctx.author, get_cmd_perm("syncroles")) and str(ctx.author.id) not in SPECIAL_USERS:
        return
    cache = resolve_role_ids(ctx.guild, force=True)
    lines = []
    for level in sorted(cache.keys()):
        roles = []
        for rid in cache[level]:
            role = ctx.guild.get_role(rid)
            if role:
                roles.append(role.mention)
        lines.append(f"**▸ Perm {level}:** {' '.join(roles) if roles else '*none*'}")
    emb = discord.Embed(
        title=f"✦ Roles Synced — {BRAND_NAME}",
        description="\n".join(lines) or "No roles matched.",
        color=THEME_COLOR,
        timestamp=datetime.now(timezone.utc),
    )
    emb.set_footer(text=f"{FOOTER_TEXT}  •  Role IDs saved")
    await ctx.send(embed=emb)

@bot.command()
async def snipe(ctx):
    data = snipe_data.get(str(ctx.channel.id))
    if not data:
        return await empty_result(ctx, "Nothing to snipe.")
    desc = censor_blacklisted(data.get("content") or "")
    if data.get("stickers"):
        desc = (desc + "\n" if desc and desc != "*attachment only*" else "") + "Sticker: " + ", ".join(data["stickers"])
    if not desc:
        desc = "*attachment only*"
    emb = discord.Embed(
        title=f"✦ Snipe — {BRAND_NAME}",
        description=desc,
        color=THEME_COLOR,
        timestamp=datetime.now(timezone.utc),
    )
    emb.add_field(name="Author", value=data["author"], inline=True)
    deleted_text = data.get("time", "unknown")
    if data.get("timestamp"):
        try:
            ts = datetime.fromisoformat(data["timestamp"])
            deleted_text = discord.utils.format_dt(ts, "R")
        except Exception:
            pass
    emb.add_field(name="Deleted", value=deleted_text, inline=True)

    # Prefer stored image_url, then any image/gif attachment (proxy_url first)
    img = data.get("image_url")
    if not img:
        for att in data.get("attachments") or []:
            fname = (att.get("filename") or "").lower()
            ctype = (att.get("content_type") or "").lower()
            is_img = ctype.startswith("image/") or fname.endswith(
                (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".gifv")
            )
            if is_img:
                img = att.get("proxy_url") or att.get("url")
                if img:
                    break
    if img:
        emb.set_image(url=img)

    other = []
    for att in data.get("attachments") or []:
        fname = (att.get("filename") or "").lower()
        ctype = (att.get("content_type") or "").lower()
        is_img = ctype.startswith("image/") or fname.endswith(
            (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".gifv")
        )
        link = att.get("proxy_url") or att.get("url")
        if not is_img and link:
            other.append(f"[{att.get('filename', 'file')}]({link})")
    if other:
        emb.add_field(name="Files", value="\n".join(other[:5]), inline=False)
    emb.set_footer(text=FOOTER_TEXT)
    await ctx.send(embed=emb)

@bot.command(aliases=["warns", "sanction"])
async def sanctions(ctx, target: str = None):
    try:
        user = None
        uid = None
        if target:
            raw = target.strip().replace("<@", "").replace("!", "").replace(">", "")
            if raw.isdigit():
                uid = raw
                try:
                    user = await bot.fetch_user(int(uid))
                except Exception:
                    user = None
            else:
                user = await get_target(ctx, target)
                if user:
                    uid = str(user.id)
        else:
            user = await get_target(ctx, None)
            if user is None:
                user = ctx.author
            uid = str(user.id)
        if not uid:
            return await ctx.send("invalid sanctions")
        lst = sanctions_data.get(str(uid), [])
        display = str(user) if user else f"User `{uid}`"
        if not lst:
            emb = discord.Embed(
                description="No sanctions received",
                color=THEME_COLOR,
                timestamp=datetime.now(timezone.utc),
            )
            if user is not None:
                avatar = getattr(getattr(user, "display_avatar", None), "url", None)
                emb.set_author(name=str(user), icon_url=avatar)
            else:
                emb.set_author(name=f"User {uid}")
            emb.set_footer(text=FOOTER_TEXT)
            return await ctx.send(embed=emb)
        # Newest first, renumber 1, 2, 3...
        ordered = list(reversed(lst))
        lines = []
        for i, s in enumerate(ordered, 1):
            date = s.get("date", "?")
            reason = s.get("reason", "No reason")
            lines.append(f"**{i}** — {date}: {reason}")
        text = "\n".join(lines)
        if len(text) > 4000:
            text = text[:4000] + "\n..."
        emb = discord.Embed(
            title=f"✦ Sanctions — {BRAND_NAME}",
            description=text,
            color=THEME_COLOR,
            timestamp=datetime.now(timezone.utc),
        )
        if user is not None:
            avatar = getattr(getattr(user, "display_avatar", None), "url", None)
            emb.set_author(name=str(user), icon_url=avatar)
            emb.set_thumbnail(url=avatar)
        else:
            emb.set_author(name=f"User {uid}")
        emb.set_footer(text=FOOTER_TEXT)
        await ctx.send(embed=emb)
    except Exception as e:
        await ctx.send(f"Failed to load sanctions: `{e}`")

@bot.command(name="del")
async def del_sanction(ctx, action: str = None, arg1: str = None, arg2: str = None):
    if action != "sanction":
        return
    if not has_perm(ctx.author, get_cmd_perm("del")):
        return
    user = None
    number = None
    if ctx.message.mentions:
        user = ctx.message.mentions[0]
    elif ctx.message.reference:
        user = await get_target(ctx, None)
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
        return await ctx.send("invalid del")
    uid = str(user.id)
    num = int(number)
    if uid not in sanctions_data or not any(s["id"] == num for s in sanctions_data[uid]):
        return await ctx.send("invalid del")
    deleted = next(s for s in sanctions_data[uid] if s["id"] == num)
    sanctions_data[uid] = [s for s in sanctions_data[uid] if s["id"] != num]
    for i, s in enumerate(sanctions_data[uid], 1):
        s["id"] = i
    save_sanctions()
    emb = discord.Embed(
        title=f"✦ Del Sanction — {BRAND_NAME}",
        description=f"Sanction deleted: **{deleted['date']}**: {deleted['reason']}",
        color=THEME_COLOR,
        timestamp=datetime.now(timezone.utc),
    )
    emb.set_footer(text=FOOTER_TEXT)
    await ctx.send(embed=emb)
    log = discord.Embed(
        title=f"✦ Del Sanction — {BRAND_NAME}",
        color=THEME_COLOR,
        timestamp=datetime.now(timezone.utc),
    )
    log.add_field(name="User", value=f"{user} (`{user.id}`)", inline=False)
    log.add_field(name="Moderator", value=f"{ctx.author} (`{ctx.author.id}`)", inline=False)
    log.add_field(name="Deleted", value=f"{deleted['date']}: {deleted['reason']}", inline=False)
    log.set_footer(text=FOOTER_TEXT)
    await send_log(log)

@bot.command()
async def warn(ctx, *, args: str = None):
    if not has_perm(ctx.author, get_cmd_perm("warn")):
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
            return await ctx.send("invalid warn")
    if not user:
        return await ctx.send("invalid warn")
    target_member = await get_member(ctx.guild, user)
    if target_member and not can_moderate(ctx.author, target_member):
        return await ctx.send("You can't warn someone with an equal or higher rank.")
    add_sanction(user.id, reason, ctx.author.id)
    emb = discord.Embed(
        title=f"✦ Warn — {BRAND_NAME}",
        description=f"{user.mention} was warned\n**Reason:** {reason}",
        color=THEME_COLOR,
        timestamp=datetime.now(timezone.utc),
    )
    emb.set_footer(text=FOOTER_TEXT)
    await ctx.send(embed=emb)
    log = discord.Embed(
        title=f"✦ Warn — {BRAND_NAME}",
        color=THEME_COLOR,
        timestamp=datetime.now(timezone.utc),
    )
    log.add_field(name="User", value=f"{user} (`{user.id}`)", inline=False)
    log.add_field(name="Moderator", value=f"{ctx.author} (`{ctx.author.id}`)", inline=False)
    log.add_field(name="Reason", value=reason, inline=False)
    log.set_footer(text=FOOTER_TEXT)
    await send_log(log)

@bot.command()
async def clearwarns(ctx, target: str = None):
    if not has_perm(ctx.author, get_cmd_perm("clearwarns")):
        return
    user = await get_target(ctx, target)
    if not user:
        return await ctx.send("invalid clearwarns")
    target_member = await get_member(ctx.guild, user)
    if target_member and not can_moderate(ctx.author, target_member):
        return await ctx.send("You can't clear warns for someone with an equal or higher rank.")
    sanctions_data[str(user.id)] = []
    save_sanctions()
    emb = discord.Embed(
        title=f"✦ Clear Warns — {BRAND_NAME}",
        description=f"Cleared all sanctions for **{user}**",
        color=THEME_COLOR,
        timestamp=datetime.now(timezone.utc),
    )
    emb.set_footer(text=FOOTER_TEXT)
    await ctx.send(embed=emb)
    log = discord.Embed(
        title=f"✦ Clear Warns — {BRAND_NAME}",
        color=THEME_COLOR,
        timestamp=datetime.now(timezone.utc),
    )
    log.add_field(name="User", value=f"{user} (`{user.id}`)", inline=False)
    log.add_field(name="Moderator", value=f"{ctx.author} (`{ctx.author.id}`)", inline=False)
    log.set_footer(text=FOOTER_TEXT)
    await send_log(log)

@bot.command()
async def tempmute(ctx, *, args: str = None):
    if not has_perm(ctx.author, get_cmd_perm("tempmute")):
        return
    if not args:
        return await ctx.send("invalid tempmute")
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
            return await ctx.send("invalid tempmute")
        user = await get_target(ctx, parts[0])
        duration = parts[1] if len(parts) > 1 else None
        reason = parts[2] if len(parts) > 2 else "No reason"
    if not user or not duration:
        return await ctx.send("invalid tempmute")
    member = await get_member(ctx.guild, user)
    if not member:
        return await ctx.send("invalid tempmute")
    if member.id == ctx.author.id:
        return await ctx.send("invalid tempmute")
    if not can_moderate(ctx.author, member):
        return await ctx.send("You can't tempmute someone with an equal or higher rank.")
    delta = parse_duration(duration)
    if not delta:
        return await ctx.send("Invalid duration (examples: `30s` `10m` `1h` `7d`)")
    if delta.total_seconds() > 28 * 86400:
        return await ctx.send("Max timeout is 28 days.")
    try:
        await member.timeout(delta, reason=reason)
        add_sanction(user.id, f"timeout {duration} - {reason}", ctx.author.id)
        emb = discord.Embed(
            title=f"✦ Tempmute — {BRAND_NAME}",
            description=f"Successfully timed out {member.mention} for **{duration}**\n**Reason:** `{reason}`",
            color=THEME_COLOR,
            timestamp=datetime.now(timezone.utc),
        )
        emb.set_footer(text=FOOTER_TEXT)
        await ctx.send(embed=emb)
        log = discord.Embed(
            title=f"✦ Tempmute — {BRAND_NAME}",
            color=THEME_COLOR,
            timestamp=datetime.now(timezone.utc),
        )
        log.add_field(name="User", value=f"{member} (`{member.id}`)", inline=False)
        log.add_field(name="Moderator", value=f"{ctx.author} (`{ctx.author.id}`)", inline=False)
        log.add_field(name="Duration", value=duration, inline=True)
        log.add_field(name="Reason", value=reason, inline=True)
        log.set_footer(text=FOOTER_TEXT)
        await send_log(log)
    except discord.Forbidden:
        await ctx.send("Missing permissions: move my role **above** the target's role and enable **Timeout Members** for me.")
    except Exception as e:
        await ctx.send(f"Failed: {e}")

@bot.command()
async def unmute(ctx, target: str = None):
    if not has_perm(ctx.author, get_cmd_perm("unmute")):
        return
    user = await get_target(ctx, target)
    if not user:
        return await ctx.send("invalid unmute")
    member = await get_member(ctx.guild, user)
    if not member:
        return await ctx.send("invalid unmute")
    if not can_moderate(ctx.author, member):
        return await ctx.send("You can't unmute someone with an equal or higher rank.")
    try:
        await member.timeout(None)
        emb = discord.Embed(
            title=f"✦ Unmute — {BRAND_NAME}",
            description=f"Unmuted {member.mention} successfully",
            color=THEME_COLOR,
            timestamp=datetime.now(timezone.utc),
        )
        emb.set_footer(text=FOOTER_TEXT)
        await ctx.send(embed=emb)
        log = discord.Embed(
            title=f"✦ Unmute — {BRAND_NAME}",
            color=THEME_COLOR,
            timestamp=datetime.now(timezone.utc),
        )
        log.add_field(name="User", value=f"{member} (`{member.id}`)", inline=False)
        log.add_field(name="Moderator", value=f"{ctx.author} (`{ctx.author.id}`)", inline=False)
        log.set_footer(text=FOOTER_TEXT)
        await send_log(log)
    except Exception as e:
        await ctx.send(f"Failed to unmute: {e}")

@bot.command()
async def mutelist(ctx):
    if not has_perm(ctx.author, get_cmd_perm("mutelist")):
        return
    muted = [m for m in ctx.guild.members if m.is_timed_out() and m.timed_out_until]
    if not muted:
        return await empty_result(ctx, "There are no muted members.")
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
    max_show = 40
    for m in muted[:max_show]:
        remaining = format_remaining(m.timed_out_until)
        lines.append(f"{m.mention} — `{remaining}`")
    description = "\n".join(lines)
    not_shown = len(muted) - max_show
    if not_shown > 0:
        description += f"\n\n*{not_shown} more not shown*"
    emb = discord.Embed(
        title=f"✦ Current Mutes — {BRAND_NAME}",
        description=description,
        color=THEME_COLOR,
        timestamp=datetime.now(timezone.utc),
    )
    emb.set_footer(text=f"{FOOTER_TEXT}  •  {len(muted)} active timeout(s)")
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
            reason = args.strip() or "No reason"
    elif args:
        parts = args.split(None, 1)
        user = await get_target(ctx, parts[0])
        if user and len(parts) > 1:
            reason = parts[1]
        elif not user:
            pass

    if not user:
        return await ctx.send("invalid ban")
    if user.id == ctx.author.id:
        return await ctx.send("invalid ban")

    try:
        dm_ok = await dm_ban_appeal(user, reason)
        await ctx.guild.ban(user, reason=reason)

        desc = f"Banned **{user}**"
        if reason and reason != "No reason":
            desc += f"\n**Reason:** {reason}"
        emb = discord.Embed(
            title=f"✦ Ban — {BRAND_NAME}",
            description=desc,
            color=THEME_COLOR,
            timestamp=datetime.now(timezone.utc),
        )
        emb.set_footer(text=FOOTER_TEXT)
        await ctx.send(embed=emb)

        log = discord.Embed(
            title=f"✦ Ban — {BRAND_NAME}",
            color=THEME_COLOR,
            timestamp=datetime.now(timezone.utc),
        )
        log.add_field(name="User", value=f"{user} (`{user.id}`)", inline=False)
        log.add_field(name="Moderator", value=f"{ctx.author} (`{ctx.author.id}`)", inline=False)
        log.add_field(name="Reason", value=reason, inline=False)
        log.add_field(name="Appeal DM", value="Sent" if dm_ok else "Failed", inline=True)
        log.set_footer(text=FOOTER_TEXT)
        await send_log(log)

    except discord.Forbidden:
        await ctx.send("I don't have permission to ban that user (check my role position + Ban Members permission).")
    except Exception as e:
        await ctx.send(f"Failed: {e}")

@bot.command()
async def appeal(ctx, *, _ignored: str = None):
    dest = ctx.author
    try:
        if ctx.guild is not None:
            await ctx.send("Check your DMs — I started your unban appeal there.")
        await start_appeal_session(dest)
    except Exception:
        await ctx.send(
            "I couldn't DM you. Open your DMs (Privacy Settings → Allow DMs from server members) and try `+appeal` again in my DMs."
        )

@bot.command()
async def unban(ctx, user_id: str = None):
    if str(ctx.author.id) not in BAN_COMMAND_USERS:
        return
    if not user_id:
        return await ctx.send("invalid unban")

    # Clean the ID (supports raw ID or mention)
    raw = user_id.strip().replace("<@", "").replace("!", "").replace(">", "")
    if not raw.isdigit():
        return await ctx.send("invalid unban")

    try:
        user = await bot.fetch_user(int(raw))
    except (ValueError, discord.NotFound, discord.HTTPException):
        return await ctx.send("invalid unban")

    try:
        await ctx.guild.unban(user)
        dm_ok = await dm_unbanned(user)
        extra = " (DM sent)" if dm_ok else " (could not DM — no mutual server or DMs closed)"
        emb = discord.Embed(
            title=f"✦ Unban — {BRAND_NAME}",
            description=f"Unbanned **{user}**{extra}",
            color=THEME_COLOR,
            timestamp=datetime.now(timezone.utc),
        )
        emb.set_footer(text=FOOTER_TEXT)
        await ctx.send(embed=emb)

        log = discord.Embed(
            title=f"✦ Unban — {BRAND_NAME}",
            color=THEME_COLOR,
            timestamp=datetime.now(timezone.utc),
        )
        log.add_field(name="User", value=f"{user} (`{user.id}`)", inline=False)
        log.add_field(name="Moderator", value=f"{ctx.author} (`{ctx.author.id}`)", inline=False)
        log.add_field(name="DM", value="Sent" if dm_ok else "Failed", inline=True)
        log.set_footer(text=FOOTER_TEXT)
        await send_log(log)

    except discord.NotFound:
        await ctx.send("This user is not banned.")
    except discord.Forbidden:
        await ctx.send("I don't have permission to unban members.")
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
            reason = args.strip() or "No reason"
    elif args:
        parts = args.split(None, 1)
        user = await get_target(ctx, parts[0])
        if user and len(parts) > 1:
            reason = parts[1]
    if not user:
        return await ctx.send("invalid kick")
    if user.id == ctx.author.id:
        return await ctx.send("invalid kick")
    member = await get_member(ctx.guild, user)
    if not member:
        return await ctx.send("invalid kick")
    if not can_moderate(ctx.author, member):
        return await ctx.send("You can't kick someone with an equal or higher rank.")
    try:
        await member.kick(reason=reason)
        desc = f"Kicked **{user}**"
        if reason and reason != "No reason":
            desc += f"\n**Reason:** {reason}"
        emb = discord.Embed(
            title=f"✦ Kick — {BRAND_NAME}",
            description=desc,
            color=THEME_COLOR,
            timestamp=datetime.now(timezone.utc),
        )
        emb.set_footer(text=FOOTER_TEXT)
        await ctx.send(embed=emb)
        log = discord.Embed(
            title=f"✦ Kick — {BRAND_NAME}",
            color=THEME_COLOR,
            timestamp=datetime.now(timezone.utc),
        )
        log.add_field(name="User", value=f"{user} (`{user.id}`)", inline=False)
        log.add_field(name="Moderator", value=f"{ctx.author} (`{ctx.author.id}`)", inline=False)
        log.add_field(name="Reason", value=reason, inline=False)
        log.set_footer(text=FOOTER_TEXT)
        await send_log(log)
    except Exception as e:
        await ctx.send(f"Failed: {e}")

@bot.command()
async def clear(ctx, *args):
    if not has_perm(ctx.author, get_cmd_perm("clear")):
        return
    amount = 10
    target = None
    if ctx.message.mentions:
        target = ctx.message.mentions[0]
        for a in reversed(args):
            if str(a).isdigit():
                amount = int(a)
                break
    elif ctx.message.reference:
        target = await get_target(ctx, None)
        if args and str(args[0]).isdigit():
            amount = int(args[0])
    elif args:
        if len(args) == 1 and str(args[0]).isdigit():
            num = int(args[0])
            if num > 10_000_000_000_000_000:
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
        if m.id == ctx.message.id:
            return True
        if target is None:
            return True
        return m.author.id == target.id
    clearing_channels.add(ctx.channel.id)
    try:
        if target is None:
            await ctx.channel.purge(limit=amount + 1, check=check)
        else:
            left = amount
            while left > 0:
                batch = min(100, left + 1)
                purged = await ctx.channel.purge(limit=batch, check=check)
                removed = sum(1 for m in purged if m.id != ctx.message.id)
                left -= max(removed, 1)
                if len(purged) < batch:
                    break
    except Exception:
        try:
            await ctx.message.delete()
        except Exception:
            pass
    finally:
        clearing_channels.discard(ctx.channel.id)

def _resolve_text_channel(ctx, channel_arg: str = None):
    """Resolve a text/voice/stage/forum channel from mention, ID, name, or current channel."""
    if channel_arg:
        raw = channel_arg.strip()
        # mention <#id>
        if raw.startswith("<#") and raw.endswith(">"):
            raw = raw[2:-1]
        if raw.isdigit():
            ch = ctx.guild.get_channel(int(raw))
            if ch is not None:
                return ch
        # name search
        name = raw.lower().lstrip("#")
        for ch in ctx.guild.channels:
            if ch.name.lower() == name:
                return ch
        for ch in ctx.guild.channels:
            if name in ch.name.lower():
                return ch
        return None
    return ctx.channel

@bot.command()
async def lock(ctx, channel: str = None):
    """Lock a channel — @everyone cannot send messages."""
    if not has_perm(ctx.author, get_cmd_perm("lock")):
        return
    ch = _resolve_text_channel(ctx, channel)
    if ch is None:
        return await ctx.send("invalid lock — channel not found")
    if not isinstance(ch, (discord.TextChannel, discord.VoiceChannel, discord.StageChannel, discord.ForumChannel, discord.Thread)):
        return await ctx.send("invalid lock — that is not a lockable channel")
    try:
        if isinstance(ch, discord.Thread):
            await ch.edit(locked=True, reason=f"Locked by {ctx.author}")
        else:
            overwrite = ch.overwrites_for(ctx.guild.default_role)
            overwrite.send_messages = False
            overwrite.add_reactions = False
            overwrite.create_public_threads = False
            overwrite.create_private_threads = False
            overwrite.send_messages_in_threads = False
            await ch.set_permissions(
                ctx.guild.default_role,
                overwrite=overwrite,
                reason=f"Locked by {ctx.author}",
            )
        emb = discord.Embed(
            title=f"✦ Lock — {BRAND_NAME}",
            description=f"Locked {ch.mention}\n@everyone can no longer send messages here.",
            color=THEME_COLOR,
            timestamp=datetime.now(timezone.utc),
        )
        emb.set_footer(text=FOOTER_TEXT)
        await ctx.send(embed=emb)
        log = discord.Embed(
            title=f"✦ Lock — {BRAND_NAME}",
            color=THEME_COLOR,
            timestamp=datetime.now(timezone.utc),
        )
        log.add_field(name="Channel", value=f"{ch.mention} (`{ch.id}`)", inline=False)
        log.add_field(name="Moderator", value=f"{ctx.author} (`{ctx.author.id}`)", inline=False)
        log.set_footer(text=FOOTER_TEXT)
        await send_log(log)
    except discord.Forbidden:
        await ctx.send("I need **Manage Channels** (and my role above the channel) to lock this.")
    except Exception as e:
        await ctx.send(f"Failed: {e}")

@bot.command()
async def unlock(ctx, channel: str = None):
    """Unlock a channel — @everyone can send messages again."""
    if not has_perm(ctx.author, get_cmd_perm("unlock")):
        return
    ch = _resolve_text_channel(ctx, channel)
    if ch is None:
        return await ctx.send("invalid unlock — channel not found")
    if not isinstance(ch, (discord.TextChannel, discord.VoiceChannel, discord.StageChannel, discord.ForumChannel, discord.Thread)):
        return await ctx.send("invalid unlock — that is not an unlockable channel")
    try:
        if isinstance(ch, discord.Thread):
            await ch.edit(locked=False, reason=f"Unlocked by {ctx.author}")
        else:
            overwrite = ch.overwrites_for(ctx.guild.default_role)
            overwrite.send_messages = None  # reset to default / inherit
            overwrite.add_reactions = None
            overwrite.create_public_threads = None
            overwrite.create_private_threads = None
            overwrite.send_messages_in_threads = None
            await ch.set_permissions(
                ctx.guild.default_role,
                overwrite=overwrite,
                reason=f"Unlocked by {ctx.author}",
            )
        emb = discord.Embed(
            title=f"✦ Unlock — {BRAND_NAME}",
            description=f"Unlocked {ch.mention}\n@everyone can send messages here again.",
            color=THEME_COLOR,
            timestamp=datetime.now(timezone.utc),
        )
        emb.set_footer(text=FOOTER_TEXT)
        await ctx.send(embed=emb)
        log = discord.Embed(
            title=f"✦ Unlock — {BRAND_NAME}",
            color=THEME_COLOR,
            timestamp=datetime.now(timezone.utc),
        )
        log.add_field(name="Channel", value=f"{ch.mention} (`{ch.id}`)", inline=False)
        log.add_field(name="Moderator", value=f"{ctx.author} (`{ctx.author.id}`)", inline=False)
        log.set_footer(text=FOOTER_TEXT)
        await send_log(log)
    except discord.Forbidden:
        await ctx.send("I need **Manage Channels** (and my role above the channel) to unlock this.")
    except Exception as e:
        await ctx.send(f"Failed: {e}")

def find_role(guild, role_query: str):
    if not role_query:
        return None
    q = role_query.strip()
    if q.startswith("<@&") and q.endswith(">"):
        rid = q[3:-1]
        if rid.isdigit():
            return guild.get_role(int(rid))
    if q.isdigit():
        role = guild.get_role(int(q))
        if role:
            return role
    q_lower = q.lower()
    role = discord.utils.find(lambda r: r.name.lower() == q_lower, guild.roles)
    if role:
        return role
    starts = [r for r in guild.roles if r.name.lower().startswith(q_lower) and r.name != "@everyone"]
    if len(starts) == 1:
        return starts[0]
    if len(starts) > 1:
        starts.sort(key=lambda r: len(r.name))
        return starts[0]
    contains = [r for r in guild.roles if q_lower in r.name.lower() and r.name != "@everyone"]
    if len(contains) == 1:
        return contains[0]
    if len(contains) > 1:
        contains.sort(key=lambda r: (len(r.name), r.name.lower()))
        return contains[0]
    return None

@bot.command()
async def temprole(ctx, *, args: str = None):
    if not has_perm(ctx.author, get_cmd_perm("temprole")):
        return
    if not args:
        return await ctx.send("invalid temprole")
    rest = args
    user = None
    if ctx.message.mentions:
        user = ctx.message.mentions[0]
        for m in ctx.message.mentions:
            rest = rest.replace(f"<@{m.id}>", "").replace(f"<@!{m.id}>", "")
    if user is None and ctx.message.reference:
        ref = ctx.message.reference
        if ref.resolved and hasattr(ref.resolved, "author"):
            user = ref.resolved.author
        elif ref.message_id:
            try:
                ref_msg = await ctx.channel.fetch_message(ref.message_id)
                user = ref_msg.author
            except Exception:
                user = await get_target(ctx, None)
    tokens = rest.strip().split()
    if not tokens:
        return await ctx.send("invalid temprole")
    if user is None and tokens[0].isdigit() and len(tokens[0]) >= 15:
        user = await get_target(ctx, tokens[0])
        tokens = tokens[1:]
    if not tokens:
        return await ctx.send("invalid temprole")
    duration = None
    duration_idx = None
    for i, tok in enumerate(tokens):
        if parse_duration(tok):
            duration = tok
            duration_idx = i
            break
    if duration is None:
        return await ctx.send("invalid temprole")
    role_tokens = tokens[:duration_idx] + tokens[duration_idx + 1:]
    role_name = " ".join(role_tokens).strip()
    if not role_name:
        return await ctx.send("invalid temprole")
    if user is None:
        user = ctx.author
    delta = parse_duration(duration)
    if not delta or delta.total_seconds() < 1:
        return await ctx.send("invalid temprole")
    member = await get_member(ctx.guild, user)
    if not member:
        return await ctx.send("invalid temprole")
    role = find_role(ctx.guild, role_name)
    if not role:
        return await ctx.send("invalid temprole")
    # Only SPECIAL_USERS can assign roles >= their own top role (and only if bot is above that role)
    if role >= ctx.author.top_role:
        if str(ctx.author.id) not in SPECIAL_USERS:
            return await ctx.send("invalid temprole")
    if role >= ctx.guild.me.top_role:
        return await ctx.send("invalid temprole")
    try:
        if role not in member.roles:
            await member.add_roles(role, reason=f"Temp role {duration} by {ctx.author}")
        ends_at = datetime.now(timezone.utc) + delta
        schedule_temprole(ctx.guild.id, member.id, role.id, ends_at)
        emb = discord.Embed(
            title=f"✦ Temp Role — {BRAND_NAME}",
            description=(
                f"Gave **{role.name}** to {member.mention} for **{duration}**\n"
                f"Removes {discord.utils.format_dt(ends_at, 'R')}"
            ),
            color=THEME_COLOR,
            timestamp=datetime.now(timezone.utc),
        )
        emb.set_footer(text=FOOTER_TEXT)
        await ctx.send(embed=emb, allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False))
        log = discord.Embed(
            title=f"✦ Temp Role — {BRAND_NAME}",
            color=THEME_COLOR,
            timestamp=datetime.now(timezone.utc),
        )
        log.add_field(name="User", value=f"{member} (`{member.id}`)", inline=False)
        log.add_field(name="Moderator", value=f"{ctx.author} (`{ctx.author.id}`)", inline=False)
        log.add_field(name="Role", value=f"{role.name} (`{role.id}`)", inline=True)
        log.add_field(name="Duration", value=duration, inline=True)
        log.set_footer(text=FOOTER_TEXT)
        await send_log(log)
    except Exception as e:
        await ctx.send(f"Failed: {e}")

@bot.command()
async def addrole(ctx, *, args: str = None):
    if not has_perm(ctx.author, get_cmd_perm("addrole")) and not has_role_manage_extra(ctx.author):
        return
    if not args:
        return await ctx.send("invalid addrole")
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
        return await ctx.send("invalid addrole")
    member = await get_member(ctx.guild, user)
    if not member:
        return await ctx.send("invalid addrole")
    role = find_role(ctx.guild, role_name)
    if not role:
        return await ctx.send("invalid addrole")
    # Only SPECIAL_USERS can assign roles >= their own top role (and only if bot is above that role)
    if role >= ctx.author.top_role:
        if str(ctx.author.id) not in SPECIAL_USERS:
            return await ctx.send("invalid addrole")
    if role >= ctx.guild.me.top_role:
        return await ctx.send("invalid addrole")
    if role in member.roles:
        return await ctx.send(f"{member.mention} already has the {role.mention} role.")
    try:
        await member.add_roles(role)
        await ctx.send("1 role was added to 1 member")
    except Exception as e:
        await ctx.send(f"Failed: {e}")

@bot.command()
async def delrole(ctx, *, args: str = None):
    if not has_perm(ctx.author, get_cmd_perm("delrole")) and not has_role_manage_extra(ctx.author):
        return
    if not args:
        return await ctx.send("invalid delrole")
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
        return await ctx.send("invalid delrole")
    member = await get_member(ctx.guild, user)
    if not member:
        return await ctx.send("invalid delrole")
    role = find_role(ctx.guild, role_name)
    if not role:
        return await ctx.send("invalid delrole")
    # Only SPECIAL_USERS can manage roles >= their own top role (and only if bot is above that role)
    if role >= ctx.author.top_role:
        if str(ctx.author.id) not in SPECIAL_USERS:
            return await ctx.send("invalid delrole")
    if role >= ctx.guild.me.top_role:
        return await ctx.send("invalid delrole")
    if role not in member.roles:
        return await ctx.send(f"{member.mention} does not have the {role.mention} role.")
    try:
        await member.remove_roles(role)
        await ctx.send("1 rôle was successfully removed from 1 member")
    except Exception as e:
        await ctx.send(f"Failed: {e}")

@bot.command()
async def derank(ctx, target: str = None):
    if not has_perm(ctx.author, get_cmd_perm("derank")):
        return
    user = await get_target(ctx, target)
    if not user:
        return await ctx.send("invalid derank")
    if user.id == ctx.author.id:
        return await ctx.send("invalid derank")
    member = await get_member(ctx.guild, user)
    if not member:
        return await ctx.send("invalid derank")
    if not can_moderate(ctx.author, member):
        return await ctx.send("You can't derank someone with an equal or higher staff rank.")
    # INSTANTLY remove ALL roles (no delay, no staff log embed, no cooldown)
    try:
        roles = [r for r in member.roles if r != ctx.guild.default_role and not r.managed]
        await member.remove_roles(*roles)
        await ctx.send(f"{member.mention} was deranked successfully")
    except Exception as e:
        await ctx.send(f"Failed: {e}")

@bot.command()
async def create(ctx, emoji: str = None, *, name: str = None):
    if not has_perm(ctx.author, get_cmd_perm("create")):
        return
    if emoji and not name:
        name = emoji
        emoji = None
    if not name:
        return await ctx.send("invalid create")
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
    if not has_perm(ctx.author, get_cmd_perm("rolemembers")):
        return
    if not role_query:
        return await ctx.send("invalid rolemembers")
    role = discord.utils.find(
        lambda r: r.name.lower() == role_query.lower() or str(r.id) == role_query,
        ctx.guild.roles
    )
    if not role:
        return await ctx.send("invalid rolemembers")
    members = role.members
    if not members:
        return await ctx.send(f"No members have the role **{role.name}**.")
    lines = [f"{m.mention} (`{m.id}`)" for m in members[:30]]
    emb = discord.Embed(
        title=f"✦ Members with {role.name}",
        description="\n".join(lines),
        color=THEME_COLOR,
        timestamp=datetime.now(timezone.utc),
    )
    emb.set_footer(text=f"{FOOTER_TEXT}  •  {len(members)} member(s)" + (f" (showing 30)" if len(members) > 30 else ""))
    await ctx.send(embed=emb)

@bot.command()
async def bl(ctx, *, args: str = None):
    if str(ctx.author.id) not in BL_COMMAND_USERS:
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
            reason = args.strip() or "No reason"
    elif args:
        parts = args.split(None, 1)
        user = await get_target(ctx, parts[0])
        if user and len(parts) > 1:
            reason = parts[1]
    if not user:
        return await ctx.send("invalid bl")
    if user.id == ctx.author.id:
        return await ctx.send("invalid bl")
    uid = str(user.id)
    if uid not in blacklist:
        blacklist.append(uid)
        save_blacklist()
    dm_ok = await dm_ban_appeal(user, reason)
    try:
        await ctx.guild.ban(user, reason=f"Blacklisted: {reason}")
    except Exception:
        pass
    if reason and reason != "No reason":
        desc = f"{user.mention} banned and blacklisted\nreason: {reason}"
    else:
        desc = f"{user.mention} banned and blacklisted"
    emb = discord.Embed(
        title=f"✦ Blacklist — {BRAND_NAME}",
        description=desc,
        color=THEME_COLOR,
        timestamp=datetime.now(timezone.utc),
    )
    emb.set_footer(text=FOOTER_TEXT)
    await ctx.send(embed=emb)
    log = discord.Embed(
        title=f"✦ Blacklist — {BRAND_NAME}",
        color=THEME_COLOR,
        timestamp=datetime.now(timezone.utc),
    )
    log.add_field(name="User", value=f"{user} (`{user.id}`)", inline=False)
    log.add_field(name="Moderator", value=f"{ctx.author} (`{ctx.author.id}`)", inline=False)
    log.add_field(name="Reason", value=reason, inline=False)
    log.add_field(name="Appeal DM", value="Sent" if dm_ok else "Failed", inline=True)
    log.set_footer(text=FOOTER_TEXT)
    await send_log(log)

@bot.command()
async def unbl(ctx, user_id: str = None):
    if str(ctx.author.id) not in BL_COMMAND_USERS:
        return
    if not user_id:
        return await ctx.send("invalid unbl")
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
        emb = discord.Embed(
            title=f"✦ Unblacklist — {BRAND_NAME}",
            description=f"Removed `{uid}` from blacklist and unbanned.{extra}",
            color=THEME_COLOR,
            timestamp=datetime.now(timezone.utc),
        )
        emb.set_footer(text=FOOTER_TEXT)
        await ctx.send(embed=emb)
        log = discord.Embed(
            title=f"✦ Unblacklist — {BRAND_NAME}",
            color=THEME_COLOR,
            timestamp=datetime.now(timezone.utc),
        )
        log.add_field(name="User", value=f"{user} (`{user.id}`)", inline=False)
        log.add_field(name="Moderator", value=f"{ctx.author} (`{ctx.author.id}`)", inline=False)
        log.add_field(name="DM", value="Sent" if dm_ok else "Failed", inline=True)
        log.set_footer(text=FOOTER_TEXT)
        await send_log(log)
    except Exception:
        await ctx.send(f"Removed `{uid}` from blacklist.")

@bot.command()
async def userinfo(ctx, target: str = None):
    user = await get_target(ctx, target) or ctx.author
    member = ctx.guild.get_member(user.id)
    emb = discord.Embed(
        title=f"✦ User Info — {BRAND_NAME}",
        color=THEME_COLOR,
        timestamp=datetime.now(timezone.utc),
    )
    emb.set_author(name=str(user), icon_url=user.display_avatar.url)
    emb.set_thumbnail(url=user.display_avatar.url)
    emb.add_field(name="ID", value=f"`{user.id}`", inline=True)
    emb.add_field(name="Created", value=discord.utils.format_dt(user.created_at, "R"), inline=True)
    if member:
        emb.add_field(name="Joined", value=discord.utils.format_dt(member.joined_at, "R"), inline=True)
        if member.premium_since:
            emb.add_field(name="Boosting", value=discord.utils.format_dt(member.premium_since, "R"), inline=True)
    emb.set_footer(text=FOOTER_TEXT)
    await ctx.send(embed=emb)

@bot.command()
async def serverinfo(ctx):
    g = ctx.guild
    emb = discord.Embed(
        title=f"✦ {g.name}",
        description=f"**{BRAND_NAME}** server overview",
        color=THEME_COLOR,
        timestamp=datetime.now(timezone.utc),
    )
    if g.icon:
        emb.set_thumbnail(url=g.icon.url)
    emb.add_field(name="Owner", value=f"<@{g.owner_id}>", inline=True)
    emb.add_field(name="Members", value=f"`{g.member_count}`", inline=True)
    emb.add_field(name="Created", value=discord.utils.format_dt(g.created_at, "R"), inline=True)
    emb.add_field(name="Boosts", value=f"`{g.premium_subscription_count or 0}`", inline=True)
    emb.add_field(name="Channels", value=f"`{len(g.channels)}`", inline=True)
    emb.add_field(name="Roles", value=f"`{len(g.roles)}`", inline=True)
    emb.set_footer(text=FOOTER_TEXT)
    await ctx.send(embed=emb)

@bot.command()
async def modstats(ctx):
    if not has_perm(ctx.author, get_cmd_perm("modstats")):
        return
    # Count sanctions issued by each moderator
    counts = {}
    for uid, entries in sanctions_data.items():
        for s in entries:
            mid = str(s.get("moderator", "0"))
            if mid and mid != "0":
                counts[mid] = counts.get(mid, 0) + 1
    if not counts:
        return await ctx.send("No moderation actions recorded yet.")
    sorted_mods = sorted(counts.items(), key=lambda x: x[1], reverse=True)[:25]
    lines = []
    for i, (mid, cnt) in enumerate(sorted_mods, 1):
        lines.append(f"**{i}.** <@{mid}> — `{cnt}` actions")
    emb = discord.Embed(
        title=f"✦ Moderator Statistics — {BRAND_NAME}",
        description="\n".join(lines),
        color=THEME_COLOR,
        timestamp=datetime.now(timezone.utc),
    )
    emb.set_footer(text=f"{FOOTER_TEXT}  •  Based on recorded sanctions / warns / timeouts")
    await ctx.send(embed=emb)

@bot.command()
async def banlist(ctx):
    if not has_perm(ctx.author, get_cmd_perm("banlist")):
        return
    try:
        bans = [entry async for entry in ctx.guild.bans(limit=50)]
    except discord.Forbidden:
        return await ctx.send("I need the **Ban Members** permission to view the ban list.")
    except Exception as e:
        return await ctx.send(f"Failed to fetch bans: {e}")
    if not bans:
        return await empty_result(ctx, "There are no banned users.")
    lines = []
    for entry in bans[:40]:
        user = entry.user
        reason = entry.reason or "No reason"
        if len(reason) > 60:
            reason = reason[:57] + "..."
        lines.append(f"**{user}** (`{user.id}`)\n↳ {reason}")
    emb = discord.Embed(
        title=f"✦ Ban List — {BRAND_NAME}",
        description="\n\n".join(lines),
        color=THEME_COLOR,
        timestamp=datetime.now(timezone.utc),
    )
    emb.set_footer(text=f"{FOOTER_TEXT}  •  {len(bans)} shown" + (" (up to 50)" if len(bans) >= 50 else ""))
    await ctx.send(embed=emb)

@bot.command()
async def baninfo(ctx, target: str = None):
    if not has_perm(ctx.author, get_cmd_perm("baninfo")):
        return
    user = await get_target(ctx, target)
    if not user:
        return await ctx.send("invalid baninfo")
    try:
        ban_entry = await ctx.guild.fetch_ban(user)
    except discord.NotFound:
        return await ctx.send(f"**{user}** is not banned.")
    except discord.Forbidden:
        return await ctx.send("I need the **Ban Members** permission to view ban info.")
    except Exception as e:
        return await ctx.send(f"Failed: {e}")
    emb = discord.Embed(
        title=f"✦ Ban Info — {BRAND_NAME}",
        color=THEME_COLOR,
        timestamp=datetime.now(timezone.utc),
    )
    emb.set_author(name=str(user), icon_url=user.display_avatar.url)
    emb.add_field(name="User", value=f"{user} (`{user.id}`)", inline=False)
    emb.add_field(name="Reason", value=ban_entry.reason or "No reason", inline=False)
    emb.set_thumbnail(url=user.display_avatar.url)
    emb.set_footer(text=FOOTER_TEXT)
    await ctx.send(embed=emb)

@bot.command()
async def changeperm(ctx, command: str = None, level: str = None):
    if not has_perm(ctx.author, get_cmd_perm("changeperm")):
        return
    if not command or level is None:
        return await ctx.send("Usage: `+changeperm <command> <level|none>`\nExample: `+changeperm warn 2` or `+changeperm clear none`")
    cmd = command.lower().strip()
    # Normalize aliases
    if cmd in ("warns",):
        cmd = "sanctions"
    if cmd in ("del sanction", "delsanction"):
        cmd = "del"
    valid_cmds = set(DEFAULT_COMMAND_PERMS.keys()) | set(command_overrides.keys())
    # Allow setting for known commands
    if level.lower() in ("none", "off", "disable", "disabled"):
        command_overrides[cmd] = "none"
        save_command_perms()
        await ctx.send(f"Permission for `{cmd}` set to **none** (disabled for regular staff).")
        return
    try:
        lvl = int(level)
        if lvl < 0 or lvl > 6:
            return await ctx.send("Level must be between 0 and 6 (or `none`).")
    except ValueError:
        return await ctx.send("Level must be a number 0-6 or `none`.")
    command_overrides[cmd] = lvl
    save_command_perms()
    await ctx.send(f"Permission for `{cmd}` set to **Perm {lvl}**.")

@bot.command()
async def help(ctx):
    emb = discord.Embed(
        title=f"✦ {BRAND_NAME} Command List",
        color=THEME_COLOR,
        description=(
            f"**Prefix:** `{PREFIX}`\n"
            "You can **reply** to a message instead of mentioning the user.\n\n"
            "**Bot maker:** Mari · **Founder:** LEO"
        ),
        timestamp=datetime.now(timezone.utc),
    )
    emb.add_field(
        name="▸ Perm 1",
        value="`+help` `+warn <member> [reason]` `+mutelist` `+perms` `+sanctions <member>` `+tempmute <member> <duration> [reason]` `+unmute <member>`",
        inline=False
    )
    emb.add_field(
        name="▸ Perm 2",
        value="`+del sanction <member> <number>` `+rolemembers <role>`",
        inline=False
    )
    emb.add_field(
        name="▸ Perm 3",
        value="`+derank <member>` `+clearwarns <member>` `+addrole <member> <role>` `+delrole <member> <role>`",
        inline=False
    )
    emb.add_field(
        name="▸ Perm 4",
        value="`+clear [number] [member]` `+lock [channel]` `+unlock [channel]` `+create [emoji] [name]`",
        inline=False
    )
    emb.add_field(
        name="▸ Perm 5",
        value="`+banlist` `+baninfo <id|mention>`",
        inline=False
    )
    emb.add_field(
        name="▸ Perm 6",
        value="`+temprole <member> <duration> <role>` `+modstats` `+changeperm <command> <level|none>` `+syncroles`",
        inline=False
    )
    emb.add_field(
        name="▸ Special Users only",
        value="`+ban` `+unban` `+kick` `+bl` `+unbl` (user ID only)",
        inline=False
    )
    emb.add_field(
        name="▸ Everyone",
        value="`+userinfo` `+serverinfo` `+snipe` `+ping`",
        inline=False
    )
    emb.set_footer(text=f"{FOOTER_TEXT}  •  Founder: LEO")
    await ctx.send(embed=emb)

# ==================== APPEAL SYSTEM ====================
async def dm_ban_appeal(user, reason: str = "No reason"):
    if user is None or getattr(user, "bot", False):
        return False
    try:
        emb = discord.Embed(
            title=f"You have been banned from {BRAND_NAME}",
            description=(
                f"**Reason:** {reason}\n\n"
                "You can **apply to get unbanned** by DMing me:\n"
                "`+appeal`\n\n"
                "I will ask for your user ID, ban reason, and why you want to be unbanned."
            ),
            color=THEME_COLOR,
        )
        emb.set_footer(text=f"{BRAND_NAME} • Unban appeals")
        await user.send(embed=emb)
        return True
    except Exception:
        try:
            await user.send(
                f"You have been banned from **{BRAND_NAME}**.\n"
                f"Reason: {reason}\n\n"
                f"To apply for an unban, DM me: `+appeal`"
            )
            return True
        except Exception:
            return False

appeal_sessions = {}

async def start_appeal_session(user):
    appeal_sessions[user.id] = {"step": "user_id", "data": {}}
    await user.send(
        f"**Unban appeal — {BRAND_NAME}**\n\n"
        "**Question 1/3:** What is your **Discord user ID**?\n"
        "(Enable Developer Mode → right-click your profile → Copy User ID)\n\n"
        "Type `cancel` anytime to stop."
    )

async def continue_appeal_session(message) -> bool:
    uid = message.author.id
    session = appeal_sessions.get(uid)
    if not session:
        return False
    text = (message.content or "").strip()
    if not text:
        return True
    if text.lower() in ("cancel", "stop", "quit"):
        appeal_sessions.pop(uid, None)
        await message.channel.send("Appeal cancelled.")
        return True
    step = session["step"]
    data = session["data"]
    if step == "user_id":
        raw = text.replace("<@", "").replace("!", "").replace(">", "").strip()
        if not raw.isdigit() or len(raw) < 15:
            await message.channel.send(
                "That doesn't look like a user ID. Send numbers only (right-click profile → Copy User ID)."
            )
            return True
        data["user_id"] = raw
        session["step"] = "ban_reason"
        await message.channel.send(
            "**Question 2/3:** What was the **reason you got banned**?\n"
            "(Write what you were banned for, as best you know.)"
        )
        return True
    if step == "ban_reason":
        if len(text) < 3:
            await message.channel.send("Please write a bit more for the ban reason.")
            return True
        data["ban_reason"] = text[:1000]
        session["step"] = "why_unban"
        await message.channel.send(
            "**Question 3/3:** **Why do you want to get unbanned?**\n"
            "(Explain why staff should unban you.)"
        )
        return True
    if step == "why_unban":
        if len(text) < 3:
            await message.channel.send("Please write a bit more about why you want to be unbanned.")
            return True
        data["why_unban"] = text[:1500]
        appeal_sessions.pop(uid, None)
        emb = discord.Embed(
            title=f"✦ Unban Appeal — {BRAND_NAME}",
            color=THEME_COLOR,
            timestamp=datetime.now(timezone.utc),
        )
        emb.add_field(name="Submitted by", value=f"{message.author} (`{message.author.id}`)", inline=False)
        emb.add_field(name="Their User ID", value=f"`{data.get('user_id', '?')}`", inline=False)
        emb.add_field(name="Reason they were banned", value=data.get("ban_reason", "?")[:1000], inline=False)
        emb.add_field(name="Why they want unbanned", value=data.get("why_unban", "?")[:1500], inline=False)
        emb.add_field(
            name="Staff action",
            value=f"`+unban {data.get('user_id', message.author.id)}`",
            inline=False,
        )
        emb.set_thumbnail(url=message.author.display_avatar.url)
        emb.set_footer(text=f"{BRAND_NAME} • Appeal")
        await send_appeal(emb)
        await message.channel.send(
            f"Your unban appeal was **sent** to {BRAND_NAME} staff.\n"
            "Please wait for a decision — do not spam appeals."
        )
        return True
    return False

async def dm_unbanned(user):
    if user is None or getattr(user, "bot", False):
        return False
    try:
        emb = discord.Embed(
            title=f"You have been unbanned — {BRAND_NAME}",
            description=(
                f"You have been **unbanned** from **{BRAND_NAME}**.\n\n"
                f"You can rejoin here: {SERVER_INVITE}"
            ),
            color=THEME_COLOR,
        )
        emb.set_footer(text=BRAND_NAME)
        await user.send(embed=emb)
        return True
    except Exception:
        try:
            await user.send(
                f"You have been unbanned from **{BRAND_NAME}**.\n"
                f"Rejoin here: {SERVER_INVITE}"
            )
            return True
        except Exception:
            return False

def censor_blacklisted(text: str) -> str:
    if not text:
        return text
    out = text
    words = sorted(BLACKLISTED_WORDS, key=len, reverse=True)
    for word in words:
        if not word:
            continue
        pattern = re.compile(re.escape(word), re.IGNORECASE)
        def _blur(m, _w=word):
            w = m.group(0)
            if len(w) <= 2:
                return "*" * len(w)
            return w[0] + ("•" * (len(w) - 2)) + w[-1]
        out = pattern.sub(_blur, out)
    return out

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

def _temprole_key(guild_id: int, user_id: int, role_id: int) -> str:
    return f"{guild_id}:{user_id}:{role_id}"

async def _remove_temprole(guild_id: int, user_id: int, role_id: int):
    key = _temprole_key(guild_id, user_id, role_id)
    _temprole_tasks.pop(key, None)
    global temproles_data
    temproles_data = [
        e for e in temproles_data
        if not (e.get("guild_id") == guild_id and e.get("user_id") == user_id and e.get("role_id") == role_id)
    ]
    save_temproles()
    guild = bot.get_guild(guild_id)
    if not guild:
        return
    member = guild.get_member(user_id)
    if not member:
        try:
            member = await guild.fetch_member(user_id)
        except Exception:
            return
    role = guild.get_role(role_id)
    if not role:
        return
    if role not in member.roles:
        return
    try:
        await member.remove_roles(role, reason="Temporary role expired")
        log = discord.Embed(
            title=f"✦ Temp Role Expired — {BRAND_NAME}",
            color=THEME_COLOR,
            timestamp=datetime.now(timezone.utc),
        )
        log.add_field(name="User", value=f"{member} (`{member.id}`)", inline=False)
        log.add_field(name="Role", value=f"{role.name} (`{role.id}`)", inline=False)
        log.set_footer(text=FOOTER_TEXT)
        await send_log(log)
    except Exception:
        pass

def schedule_temprole(guild_id: int, user_id: int, role_id: int, ends_at: datetime):
    import asyncio
    key = _temprole_key(guild_id, user_id, role_id)
    old = _temprole_tasks.pop(key, None)
    if old and not old.done():
        old.cancel()
    now = datetime.now(timezone.utc)
    if ends_at.tzinfo is None:
        ends_at = ends_at.replace(tzinfo=timezone.utc)
    delay = max(0, (ends_at - now).total_seconds())
    async def _runner():
        try:
            await asyncio.sleep(delay)
            await _remove_temprole(guild_id, user_id, role_id)
        except asyncio.CancelledError:
            return
    _temprole_tasks[key] = asyncio.create_task(_runner())
    global temproles_data
    temproles_data = [
        e for e in temproles_data
        if not (e.get("guild_id") == guild_id and e.get("user_id") == user_id and e.get("role_id") == role_id)
    ]
    temproles_data.append({
        "guild_id": guild_id,
        "user_id": user_id,
        "role_id": role_id,
        "ends_at": ends_at.isoformat(),
    })
    save_temproles()

async def restore_temproles():
    import asyncio
    now = datetime.now(timezone.utc)
    pending = list(temproles_data)
    for entry in pending:
        try:
            gid = int(entry["guild_id"])
            uid = int(entry["user_id"])
            rid = int(entry["role_id"])
            ends = datetime.fromisoformat(entry["ends_at"])
            if ends.tzinfo is None:
                ends = ends.replace(tzinfo=timezone.utc)
            if ends <= now:
                await _remove_temprole(gid, uid, rid)
            else:
                schedule_temprole(gid, uid, rid, ends)
        except Exception as e:
            print(f"temprole restore error: {e}")

async def send_log(embed: discord.Embed):
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

async def send_message_log(embed: discord.Embed):
    """Send message delete / edit / bulk-delete panels to the message log channel."""
    ch = bot.get_channel(MESSAGE_LOG_CHANNEL_ID)
    if ch is None:
        try:
            ch = await bot.fetch_channel(MESSAGE_LOG_CHANNEL_ID)
        except Exception:
            return
    try:
        await ch.send(embed=embed)
    except Exception:
        pass

async def send_appeal(embed: discord.Embed):
    ch = bot.get_channel(APPEAL_CHANNEL_ID)
    if ch is None:
        try:
            ch = await bot.fetch_channel(APPEAL_CHANNEL_ID)
        except Exception:
            await send_log(embed)
            return
    try:
        await ch.send(embed=embed)
    except Exception:
        await send_log(embed)

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
    if ctx.message.mentions:
        return ctx.message.mentions[0]
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
    if arg:
        arg = arg.strip()
        if arg.isdigit():
            try:
                return await bot.fetch_user(int(arg))
            except Exception:
                pass
        if arg.startswith("<@") and arg.endswith(">"):
            raw = arg.replace("<@", "").replace("!", "").replace(">", "")
            if raw.isdigit():
                try:
                    return await bot.fetch_user(int(raw))
                except Exception:
                    pass
        if ctx.guild:
            name = arg.lower()
            for m in ctx.guild.members:
                if (
                    m.name.lower() == name
                    or (m.display_name and m.display_name.lower() == name)
                    or str(m).lower() == name
                ):
                    return m
            for m in ctx.guild.members:
                if m.name.lower().startswith(name) or (m.display_name and m.display_name.lower().startswith(name)):
                    return m
    return None

async def get_member(guild: discord.Guild, user):
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
    """Send a reply that stays (does not delete the command or the response)."""
    try:
        emb = discord.Embed(
            description=text,
            color=THEME_COLOR,
            timestamp=datetime.now(timezone.utc),
        )
        emb.set_footer(text=FOOTER_TEXT)
        await ctx.send(embed=emb)
    except Exception:
        try:
            await ctx.send(text)
        except Exception:
            pass

SERVER_INVITE = "https://discord.gg/GtRfjpAjsA"

# ==================== KEEP-ALIVE ====================
class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Bot is online")

    def log_message(self, format, *args):
        return

def start_keep_alive():
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
