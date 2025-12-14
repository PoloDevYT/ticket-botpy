import os
import io
import sqlite3
from datetime import datetime, timezone

import discord
from discord.ext import commands

COMMAND_PREFIX = "r!"
DB_FILE = "tickets.db"

DEFAULT_CATEGORY_NAMES = {
    "support": "📩 Tickets - Suporte",
    "financeiro": "💰 Tickets - Financeiro",
    "modcreator": "🧩 Tickets - ModCreator",
    "modelcreator": "🎭 Tickets - ModelCreator",
}

DEFAULT_PANEL_CHANNEL_NAME = "painel-ticket"

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix=COMMAND_PREFIX, intents=intents)

conn = sqlite3.connect(DB_FILE)
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS guild_config (
    guild_id INTEGER PRIMARY KEY,
    panel_channel_id INTEGER,
    log_channel_id INTEGER,
    staff_role_id INTEGER
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS categories (
    guild_id INTEGER,
    key TEXT,
    category_id INTEGER,
    name TEXT,
    PRIMARY KEY (guild_id, key)
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS tickets (
    guild_id INTEGER,
    user_id INTEGER,
    category_key TEXT,
    channel_id INTEGER,
    created_at TEXT,
    PRIMARY KEY (guild_id, user_id, category_key)
)
""")

conn.commit()


def get_guild_config(guild_id: int):
    cur.execute(
        "SELECT panel_channel_id, log_channel_id, staff_role_id FROM guild_config WHERE guild_id=?",
        (guild_id,),
    )
    row = cur.fetchone()
    if not row:
        return {"panel_channel_id": None, "log_channel_id": None, "staff_role_id": None}
    return {"panel_channel_id": row[0], "log_channel_id": row[1], "staff_role_id": row[2]}


def upsert_guild_config(guild_id: int, panel_channel_id=None, log_channel_id=None, staff_role_id=None):
    existing = get_guild_config(guild_id)
    panel_channel_id = panel_channel_id if panel_channel_id is not None else existing["panel_channel_id"]
    log_channel_id = log_channel_id if log_channel_id is not None else existing["log_channel_id"]
    staff_role_id = staff_role_id if staff_role_id is not None else existing["staff_role_id"]

    cur.execute(
        """
        INSERT INTO guild_config (guild_id, panel_channel_id, log_channel_id, staff_role_id)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(guild_id) DO UPDATE SET
          panel_channel_id=excluded.panel_channel_id,
          log_channel_id=excluded.log_channel_id,
          staff_role_id=excluded.staff_role_id
        """,
        (guild_id, panel_channel_id, log_channel_id, staff_role_id),
    )
    conn.commit()


def set_category(guild_id: int, key: str, category_id: int, name: str):
    cur.execute(
        """
        INSERT INTO categories (guild_id, key, category_id, name)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(guild_id, key) DO UPDATE SET
          category_id=excluded.category_id,
          name=excluded.name
        """,
        (guild_id, key, category_id, name),
    )
    conn.commit()


def get_category_id(guild_id: int, key: str):
    cur.execute("SELECT category_id, name FROM categories WHERE guild_id=? AND key=?", (guild_id, key))
    row = cur.fetchone()
    if not row:
        return None, None
    return row[0], row[1]


def has_open_ticket(guild_id: int, user_id: int, category_key: str) -> bool:
    cur.execute(
        "SELECT 1 FROM tickets WHERE guild_id=? AND user_id=? AND category_key=?",
        (guild_id, user_id, category_key),
    )
    return cur.fetchone() is not None


def save_ticket(guild_id: int, user_id: int, category_key: str, channel_id: int):
    cur.execute(
        """
        INSERT OR REPLACE INTO tickets (guild_id, user_id, category_key, channel_id, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (guild_id, user_id, category_key, channel_id, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()


def delete_ticket_by_channel(guild_id: int, channel_id: int):
    cur.execute("DELETE FROM tickets WHERE guild_id=? AND channel_id=?", (guild_id, channel_id))
    conn.commit()


def get_ticket_by_channel(guild_id: int, channel_id: int):
    cur.execute(
        """
        SELECT user_id, category_key, created_at FROM tickets
        WHERE guild_id=? AND channel_id=?
        """,
        (guild_id, channel_id),
    )
    row = cur.fetchone()
    if not row:
        return None
    return {"user_id": row[0], "category_key": row[1], "created_at": row[2]}


def is_staff(member: discord.Member, guild_cfg: dict) -> bool:
    if member.guild_permissions.administrator:
        return True
    staff_role_id = guild_cfg.get("staff_role_id")
    if staff_role_id and any(r.id == staff_role_id for r in member.roles):
        return True
    return False


async def log_event(guild: discord.Guild, text: str, *, embed: discord.Embed | None = None):
    cfg = get_guild_config(guild.id)
    log_channel_id = cfg.get("log_channel_id")
    if not log_channel_id:
        return
    ch = guild.get_channel(log_channel_id)
    if isinstance(ch, discord.TextChannel):
        try:
            await ch.send(content=text, embed=embed)
        except Exception:
            pass


async def get_or_create_category(guild: discord.Guild, key: str, desired_name: str) -> discord.CategoryChannel:
    cat_id, _ = get_category_id(guild.id, key)
    if cat_id:
        ch = guild.get_channel(cat_id)
        if isinstance(ch, discord.CategoryChannel):
            return ch

    for c in guild.categories:
        if c.name.lower() == desired_name.lower():
            set_category(guild.id, key, c.id, c.name)
            return c

    cat = await guild.create_category(name=desired_name, reason="Setup automático: categorias do sistema de tickets")
    set_category(guild.id, key, cat.id, cat.name)
    return cat


async def get_or_create_text_channel(
    guild: discord.Guild, name: str, category: discord.CategoryChannel | None
) -> discord.TextChannel:
    for ch in guild.text_channels:
        if ch.name.lower() == name.lower():
            if category is None or ch.category_id == category.id:
                return ch
    return await guild.create_text_channel(name=name, category=category, reason="Setup automático: canal")


def ticket_embed_open(member: discord.Member, category_key: str) -> discord.Embed:
    titles = {
        "support": "🎫 Ticket - Suporte",
        "financeiro": "🎫 Ticket - Financeiro",
        "modcreator": "🎫 Ticket - ModCreator",
        "modelcreator": "🎫 Ticket - ModelCreator",
    }
    emb = discord.Embed(
        title=titles.get(category_key, "🎫 Ticket"),
        description=(
            f"Olá {member.mention}! Seu ticket foi criado.\n\n"
            f"✅ Aguarde atendimento da equipe.\n"
            f"🔒 Para fechar, clique em **Fechar**."
        ),
        color=discord.Color.yellow(),
    )
    emb.set_footer(text="KiraBot - Ticket System")
    return emb


async def fetch_transcript(channel: discord.TextChannel, limit: int = 1500) -> str:
    lines = []
    async for msg in channel.history(limit=limit, oldest_first=True):
        ts = msg.created_at.replace(tzinfo=timezone.utc).astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        author = f"{msg.author} ({msg.author.id})"
        content = msg.content or ""
        if msg.attachments:
            att = " | ".join(a.url for a in msg.attachments)
            content = f"{content}\n[anexos] {att}".strip()
        if msg.embeds:
            content = f"{content}\n[embeds] {len(msg.embeds)} embed(s)".strip()
        lines.append(f"[{ts}] {author}: {content}")
    return "\n".join(lines) if lines else "(sem mensagens)"


class CloseTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Fechar", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="ticket:close")
    async def close(self, interaction: discord.Interaction, _: discord.ui.Button):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Isso só funciona no servidor.", ephemeral=True)

        if not isinstance(interaction.channel, discord.TextChannel):
            return await interaction.response.send_message("Canal inválido.", ephemeral=True)

        guild = interaction.guild
        cfg = get_guild_config(guild.id)

        ticket = get_ticket_by_channel(guild.id, interaction.channel.id)
        if not ticket:
            return await interaction.response.send_message("Ticket não encontrado no banco.", ephemeral=True)

        owner_id = ticket["user_id"]
        if not is_staff(interaction.user, cfg) and interaction.user.id != owner_id:
            return await interaction.response.send_message("Você não pode fechar este ticket.", ephemeral=True)

        category_key = ticket["category_key"]
        created_at = ticket["created_at"]

        await interaction.response.send_message("Fechando ticket e gerando transcrição…", ephemeral=True)

        transcript_txt = await fetch_transcript(interaction.channel, limit=1500)
        file_name = f"transcript-{guild.id}-{interaction.channel.id}.txt"
        transcript_file = discord.File(io.BytesIO(transcript_txt.encode("utf-8")), filename=file_name)

        owner = guild.get_member(owner_id)
        emb = discord.Embed(title="🔒 Ticket fechado", color=discord.Color.red())
        emb.add_field(name="Canal", value=f"{interaction.channel.name} (`{interaction.channel.id}`)", inline=False)
        emb.add_field(name="Categoria", value=category_key, inline=True)
        emb.add_field(name="Aberto em", value=created_at, inline=True)
        emb.add_field(name="Fechado por", value=f"{interaction.user} (`{interaction.user.id}`)", inline=False)
        if owner:
            emb.add_field(name="Dono", value=f"{owner} (`{owner.id}`)", inline=False)

        await log_event(guild, "📌 Transcrição anexada abaixo.", embed=emb)

        cfg2 = get_guild_config(guild.id)
        log_channel_id = cfg2.get("log_channel_id")
        log_ch = guild.get_channel(log_channel_id) if log_channel_id else None
        if isinstance(log_ch, discord.TextChannel):
            await log_ch.send(file=transcript_file)

        delete_ticket_by_channel(guild.id, interaction.channel.id)
        try:
            await interaction.channel.delete(reason="Ticket fechado")
        except Exception:
            await log_event(guild, f"⚠️ Não consegui deletar o canal `{interaction.channel.id}`. Verifique permissões.")


class TicketCategorySelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Financeiro", value="financeiro", description="Abrir ticket financeiro"),
            discord.SelectOption(label="ModCreator", value="modcreator", description="Abrir ticket ModCreator"),
            discord.SelectOption(label="ModelCreator", value="modelcreator", description="Abrir ticket ModelCreator"),
        ]
        super().__init__(
            placeholder="Selecione o ticket que deseja!",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="ticket:category_select",
        )

    async def callback(self, interaction: discord.Interaction):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Isso só funciona no servidor.", ephemeral=True)

        guild = interaction.guild
        member = interaction.user
        category_key = self.values[0]

        if has_open_ticket(guild.id, member.id, category_key):
            return await interaction.response.send_message("Você já possui um ticket dessa categoria aberto.", ephemeral=True)

        cat = await get_or_create_category(guild, category_key, DEFAULT_CATEGORY_NAMES[category_key])
        cfg = get_guild_config(guild.id)

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            member: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True, read_message_history=True),
        }

        staff_role_id = cfg.get("staff_role_id")
        if staff_role_id:
            role = guild.get_role(staff_role_id)
            if role:
                overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)

        safe_name = member.display_name.lower().replace(" ", "-")
        channel_name = f"{category_key}-{safe_name}"

        try:
            channel = await guild.create_text_channel(
                name=channel_name,
                category=cat,
                overwrites=overwrites,
                reason="Ticket criado via painel",
            )
        except Exception as e:
            await log_event(guild, f"❌ Erro ao criar ticket ({category_key}) para {member.id}: {e}")
            return await interaction.response.send_message(f"Erro ao criar ticket: {e}", ephemeral=True)

        save_ticket(guild.id, member.id, category_key, channel.id)
        await channel.send(content=member.mention, embed=ticket_embed_open(member, category_key), view=CloseTicketView())
        await log_event(guild, f"✅ Ticket criado: {channel.mention} | cat={category_key} | user={member} ({member.id})")
        await interaction.response.send_message("Ticket criado com sucesso! ✅", ephemeral=True)


class TicketPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketCategorySelect())

    @discord.ui.button(
        label="Abrir ticket (Suporte)", style=discord.ButtonStyle.success, emoji="⭐", custom_id="ticket:open_support"
    )
    async def open_support(self, interaction: discord.Interaction, _: discord.ui.Button):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Isso só funciona no servidor.", ephemeral=True)

        guild = interaction.guild
        member = interaction.user
        category_key = "support"

        if has_open_ticket(guild.id, member.id, category_key):
            return await interaction.response.send_message("Você já possui um ticket de suporte aberto.", ephemeral=True)

        cat = await get_or_create_category(guild, category_key, DEFAULT_CATEGORY_NAMES[category_key])
        cfg = get_guild_config(guild.id)

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            member: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True, read_message_history=True),
        }

        staff_role_id = cfg.get("staff_role_id")
        if staff_role_id:
            role = guild.get_role(staff_role_id)
            if role:
                overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)

        safe_name = member.display_name.lower().replace(" ", "-")
        channel_name = f"suporte-{safe_name}"

        try:
            channel = await guild.create_text_channel(
                name=channel_name,
                category=cat,
                overwrites=overwrites,
                reason="Ticket de suporte criado via painel",
            )
        except Exception as e:
            await log_event(guild, f"❌ Erro ao criar suporte para {member.id}: {e}")
            return await interaction.response.send_message(f"Erro ao criar ticket: {e}", ephemeral=True)

        save_ticket(guild.id, member.id, category_key, channel.id)
        await channel.send(content=member.mention, embed=ticket_embed_open(member, category_key), view=CloseTicketView())
        await log_event(guild, f"✅ Ticket criado: {channel.mention} | cat=support | user={member} ({member.id})")
        await interaction.response.send_message("Ticket criado com sucesso! ✅", ephemeral=True)


class VerifyView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Verificar", style=discord.ButtonStyle.success, custom_id="verify:button")
    async def verify(self, interaction: discord.Interaction, _: discord.ui.Button):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Isso só funciona no servidor.", ephemeral=True)

        guild = interaction.guild
        member = interaction.user

        role_name = "✅ Verificado"
        role = discord.utils.get(guild.roles, name=role_name)
        if role is None:
            try:
                role = await guild.create_role(name=role_name, reason="Setup automático: cargo de verificação")
            except Exception as e:
                await log_event(guild, f"❌ Erro ao criar cargo verificado: {e}")
                return await interaction.response.send_message("Não consegui criar o cargo de verificação.", ephemeral=True)

        if role in member.roles:
            return await interaction.response.send_message("Você já está verificado.", ephemeral=True)

        try:
            await member.add_roles(role, reason="Verificação via botão")
        except Exception as e:
            await log_event(guild, f"❌ Erro ao dar cargo verificado: {e}")
            return await interaction.response.send_message("Falha ao aplicar o cargo. Verifique permissões do bot.", ephemeral=True)

        await log_event(guild, f"✅ Verificação: {member} ({member.id}) recebeu {role.name}")
        await interaction.response.send_message("Você foi verificado com sucesso ✅", ephemeral=True)


def admin_only():
    async def predicate(ctx: commands.Context):
        return ctx.guild is not None and ctx.author.guild_permissions.administrator
    return commands.check(predicate)


@bot.command(name="setup_staff")
@admin_only()
async def setup_staff(ctx: commands.Context, role: discord.Role):
    upsert_guild_config(ctx.guild.id, staff_role_id=role.id)
    await ctx.reply(f"✅ Cargo de staff definido: {role.mention}")


@bot.command(name="setup_logs")
@admin_only()
async def setup_logs(ctx: commands.Context, channel: discord.TextChannel):
    upsert_guild_config(ctx.guild.id, log_channel_id=channel.id)
    await ctx.reply(f"✅ Canal de logs definido: {channel.mention}")


@bot.command(name="setup_panel")
@admin_only()
async def setup_panel(ctx: commands.Context, channel: discord.TextChannel | None = None):
    channel = channel or ctx.channel
    upsert_guild_config(ctx.guild.id, panel_channel_id=channel.id)
    await ctx.reply(f"✅ Canal do painel definido: {channel.mention}")


@bot.command(name="post_ticket")
@admin_only()
async def post_ticket(ctx: commands.Context):
    await ensure_guild_setup(ctx.guild)

    emb = discord.Embed(
        title="🎫 Sistema de Tickets",
        description="Use o botão para abrir ticket de suporte ou escolha uma categoria no menu.",
        color=discord.Color.blue(),
    )
    await ctx.send(embed=emb, view=TicketPanelView())


@bot.command(name="post_verificar")
@admin_only()
async def post_verificar(ctx: commands.Context):
    emb = discord.Embed(
        title="✅ Verificação",
        description="Clique no botão para se verificar e receber acesso aos canais.",
        color=discord.Color.green(),
    )
    await ctx.send(embed=emb, view=VerifyView())


@bot.command(name="help_ticket")
async def help_ticket(ctx: commands.Context):
    txt = (
        "**Comandos (Admin do servidor):**\n"
        f"- `{COMMAND_PREFIX}setup_staff @Cargo` → define o cargo de quem atende tickets\n"
        f"- `{COMMAND_PREFIX}setup_logs #canal` → define onde o bot envia logs e transcrições\n"
        f"- `{COMMAND_PREFIX}setup_panel #canal` → define onde você quer postar os painéis\n"
        f"- `{COMMAND_PREFIX}post_ticket` → posta o painel de tickets\n"
        f"- `{COMMAND_PREFIX}post_verificar` → posta o painel de verificação\n\n"
        "**Uso (membros):**\n"
        "- Abra um ticket no painel e aguarde atendimento.\n"
        "- Para fechar, clique em **Fechar** (dono do ticket ou staff).\n"
    )
    await ctx.reply(txt)


async def ensure_guild_setup(guild: discord.Guild):
    for key, name in DEFAULT_CATEGORY_NAMES.items():
        await get_or_create_category(guild, key, name)

    cfg = get_guild_config(guild.id)
    panel_id = cfg.get("panel_channel_id")

    support_cat = await get_or_create_category(guild, "support", DEFAULT_CATEGORY_NAMES["support"])
    if not panel_id:
        panel_ch = await get_or_create_text_channel(guild, DEFAULT_PANEL_CHANNEL_NAME, support_cat)
        upsert_guild_config(guild.id, panel_channel_id=panel_ch.id)


@bot.event
async def on_ready():
    print(f"✅ Conectado como {bot.user} (ID: {bot.user.id})")
    for guild in bot.guilds:
        try:
            await ensure_guild_setup(guild)
        except Exception as e:
            print(f"Falha no setup do servidor {guild.id}: {e}")


if __name__ == "__main__":
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("Defina a variável de ambiente DISCORD_TOKEN com o token do bot.")
    bot.run(token)
