
import os
import secrets
import sqlite3
import requests
from flask import Flask, render_template, session, redirect, request, url_for, flash
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Configurações do Discord
CLIENT_ID = os.getenv("DISCORD_CLIENT_ID")
CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET")
REDIRECT_URI = os.getenv("DISCORD_REDIRECT_URI", "http://localhost:5000/callback")
API_BASE_URL = "https://discord.com/api/v10"
DB_FILE = "tickets.db"

def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def get_user_admin_guilds(access_token):
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get(f"{API_BASE_URL}/users/@me/guilds", headers=headers)

    if response.status_code != 200:
        return []

    admin_guilds = []
    for guild in response.json():
        perms = int(guild.get("permissions", 0))
        if perms & 0x8:
            admin_guilds.append(guild)

    return admin_guilds


def get_authorized_guild(guild_id):
    if "token" not in session:
        return None

    for guild in get_user_admin_guilds(session["token"]):
        if guild.get("id") == str(guild_id):
            return guild

    return None


def get_csrf_token():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    return session["csrf_token"]


@app.route("/")
def index():
    if "user" not in session:
        return render_template("index.html")

    admin_guilds = get_user_admin_guilds(session["token"])

    bot_token = os.getenv("DISCORD_TOKEN")
    bot_guilds_ids = set()
    if bot_token:
        headers_bot = {"Authorization": f"Bot {bot_token}"}
        r_bot = requests.get(f"{API_BASE_URL}/users/@me/guilds?limit=200", headers=headers_bot)
        if r_bot.status_code == 200:
            bot_guilds_ids = {g["id"] for g in r_bot.json()}

    for guild in admin_guilds:
        guild["has_bot"] = guild["id"] in bot_guilds_ids

    return render_template("index.html", guilds=admin_guilds, client_id=CLIENT_ID)

@app.route("/login")
def login():
    if not CLIENT_ID or not CLIENT_SECRET:
        return "Configure DISCORD_CLIENT_ID e DISCORD_CLIENT_SECRET no .env", 500
        
    scope = "identify guilds"
    discord_login_url = (
        f"https://discord.com/api/oauth2/authorize?client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}&response_type=code&scope={scope}"
    )
    return redirect(discord_login_url)

@app.route("/callback")
def callback():
    code = request.args.get("code")
    data = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "scope": "identify guilds"
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    r = requests.post(f"{API_BASE_URL}/oauth2/token", data=data, headers=headers)
    
    if r.status_code != 200:
        return f"Erro no login: {r.text}", 400
        
    token_json = r.json()
    access_token = token_json["access_token"]
    
    user_headers = {"Authorization": f"Bearer {access_token}"}
    r_user = requests.get(f"{API_BASE_URL}/users/@me", headers=user_headers)
    
    if r_user.status_code == 200:
        user_data = r_user.json()
        user_data["avatar_url"] = f"https://cdn.discordapp.com/avatars/{user_data['id']}/{user_data['avatar']}.png"
        session["user"] = user_data
        session["token"] = access_token
        return redirect("/")
        
    return "Erro ao obter dados do usuário", 400

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

@app.route("/server/<int:guild_id>")
def server_dashboard(guild_id):
    if "user" not in session:
        return redirect("/")

    guild = get_authorized_guild(guild_id)
    if not guild:
        flash("Você não tem permissão para acessar este servidor.", "error")
        return redirect("/")

    conn = get_db_connection()

    stats = {
        "open_tickets": conn.execute("SELECT COUNT(*) FROM tickets WHERE guild_id=?", (guild_id,)).fetchone()[0],
        "total_tickets": conn.execute("SELECT COUNT(*) FROM tickets WHERE guild_id=?", (guild_id,)).fetchone()[0],
        "support": conn.execute("SELECT COUNT(*) FROM tickets WHERE guild_id=? AND category_key='support'", (guild_id,)).fetchone()[0],
        "finance": conn.execute("SELECT COUNT(*) FROM tickets WHERE guild_id=? AND category_key='financeiro'", (guild_id,)).fetchone()[0],
        "modcreator": conn.execute("SELECT COUNT(*) FROM tickets WHERE guild_id=? AND category_key='modcreator'", (guild_id,)).fetchone()[0],
        "modelcreator": conn.execute("SELECT COUNT(*) FROM tickets WHERE guild_id=? AND category_key='modelcreator'", (guild_id,)).fetchone()[0],
        "formstaff": conn.execute("SELECT COUNT(*) FROM tickets WHERE guild_id=? AND category_key='formstaff'", (guild_id,)).fetchone()[0],
    }

    config_row = conn.execute("SELECT * FROM guild_config WHERE guild_id=?", (guild_id,)).fetchone()
    config = dict(config_row) if config_row else {}

    recent_tickets = conn.execute("SELECT * FROM tickets WHERE guild_id=?", (guild_id,)).fetchall()

    conn.close()

    guild_name = guild.get("name") or f"Servidor {guild_id}"
    
    return render_template("dashboard.html", guild_id=guild_id, guild_name=guild_name, stats=stats, config=config, recent_tickets=recent_tickets, csrf_token=get_csrf_token())

@app.route("/server/<int:guild_id>/config", methods=["POST"])
def update_config(guild_id):
    if "user" not in session:
        return redirect("/")
    
    if not get_authorized_guild(guild_id):
        flash("Você não tem permissão para alterar as configurações deste servidor.", "error")
        return redirect("/")

    if request.form.get("csrf_token") != session.get("csrf_token"):
        flash("Token CSRF inválido. Tente novamente.", "error")
        return redirect(url_for("server_dashboard", guild_id=guild_id))
        
    log_channel_id = request.form.get("log_channel_id")
    staff_role_id = request.form.get("staff_role_id")
    
    conn = get_db_connection()
    conn.execute("""
        INSERT INTO guild_config (guild_id, log_channel_id, staff_role_id)
        VALUES (?, ?, ?)
        ON CONFLICT(guild_id) DO UPDATE SET
          log_channel_id=excluded.log_channel_id,
          staff_role_id=excluded.staff_role_id
    """, (guild_id, log_channel_id, staff_role_id))
    conn.commit()
    conn.close()
    
    flash("Configurações salvas com sucesso!", "success")
    return redirect(url_for("server_dashboard", guild_id=guild_id))

if __name__ == "__main__":
    app.run(debug=True, port=5000)
