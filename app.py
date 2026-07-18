from flask import Flask, request, redirect
import requests
import sqlite3
import secrets
import os

app = Flask(__name__)

CLIENT_ID = "YOUR_CLIENT_ID"
CLIENT_SECRET = "YOUR_CLIENT_SECRET"
REDIRECT_URI = "https://yourdomain.com/callback"
BOT_TOKEN = "YOUR_BOT_TOKEN"

# --- ตั้งค่าฐานข้อมูล ---
conn = sqlite3.connect("servers.db", check_same_thread=False)
conn.execute("""
CREATE TABLE IF NOT EXISTS server_config (
    guild_id TEXT PRIMARY KEY,
    role_id TEXT NOT NULL
)
""")
conn.commit()

pending_verifications = {}


def add_server(guild_id, role_id):
    conn.execute(
        "INSERT OR REPLACE INTO server_config (guild_id, role_id) VALUES (?, ?)",
        (guild_id, role_id)
    )
    conn.commit()


@app.route("/")
def home():
    return "Bot verify server is running."


@app.route("/verify")
def verify():
    guild_id = request.args.get("guild_id")
    if not guild_id:
        return "ต้องระบุ guild_id", 400

    row = conn.execute(
        "SELECT role_id FROM server_config WHERE guild_id = ?", (guild_id,)
    ).fetchone()

    if not row:
        return "เซิร์ฟนี้ยังไม่ได้ตั้งค่าไว้", 400

    role_id = row[0]

    verify_token = secrets.token_urlsafe(16)
    pending_verifications[verify_token] = {"guild_id": guild_id, "role_id": role_id}

    discord_auth_url = (
        f"https://discord.com/api/oauth2/authorize"
        f"?client_id={CLIENT_ID}"
        f"&redirect_uri={REDIRECT_URI}"
        f"&response_type=code"
        f"&scope=identify+guilds.join"
        f"&state={verify_token}"
    )
    return redirect(discord_auth_url)


@app.route("/callback")
def callback():
    code = request.args.get("code")
    verify_token = request.args.get("state")

    if not code or not verify_token:
        return "ข้อมูลไม่ครบ", 400

    data = pending_verifications.pop(verify_token, None)
    if not data:
        return "ลิงก์หมดอายุหรือไม่ถูกต้อง", 400

    guild_id = data["guild_id"]
    role_id = data["role_id"]

    token_res = requests.post(
        "https://discord.com/api/oauth2/token",
        data={
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    token_data = token_res.json()
    access_token = token_data.get("access_token")
    if not access_token:
        return f"แลก token ไม่สำเร็จ: {token_data}", 400

    user_res = requests.get(
        "https://discord.com/api/users/@me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    user_id = user_res.json()["id"]

    payload = {"access_token": access_token}
    if role_id:
        payload["roles"] = [role_id]

    add_res = requests.put(
        f"https://discord.com/api/guilds/{guild_id}/members/{user_id}",
        headers={
            "Authorization": f"Bot {BOT_TOKEN}",
            "Content-Type": "application/json",
        },
        json=payload,
    )

    if add_res.status_code in (201, 204):
        return "เข้าเซิร์ฟสำเร็จแล้ว! กลับไปที่ Discord ได้เลย 🎉"
    else:
        return f"เกิดข้อผิดพลาด: {add_res.status_code} {add_res.text}", 400


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
