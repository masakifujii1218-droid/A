from datetime import datetime, timedelta
import json
import os
import random
import threading
import time

# ==========================================
# Flask (ダミー定義含む)
# ==========================================
try:
    from flask import Flask
except ModuleNotFoundError:
    class Flask:
        def __init__(self, name):
            self.name = name
            self.routes = {}

        def route(self, path):
            def decorator(func):
                self.routes[path] = func
                return func
            return decorator

        def run(self, *args, **kwargs):
            pass

        def test_client(self):
            class Client:
                def __init__(self, app):
                    self.app = app

                def get(self, path):
                    body = self.app.routes[path]()
                    return type(
                        "Response",
                        (),
                        {
                            "status_code": 200,
                            "get_data": lambda self, as_text=False: body
                        }
                    )()
            return Client(self)

# ==========================================
# Discord (ダミー定義含む)
# ==========================================
try:
    import discord
    from discord.ext import commands
    from discord import app_commands
except ModuleNotFoundError:
    class DummyChoice:
        def __init__(self, name=None, value=None):
            self.name = name
            self.value = value

        def __class_getitem__(cls, item):
            return cls

    class DummyAppCommands:
        @staticmethod
        def choices(**kwargs):
            def deco(func):
                return func
            return deco
        Choice = DummyChoice

    class DummyIntents:
        members = False
        message_content = False  # ダミー側にもプロパティを追加
        @staticmethod
        def default():
            return DummyIntents()

    class DummyUI:
        class View:
            def __init__(self, *args, **kwargs):
                pass
        class Modal:
            def __init__(self, *args, **kwargs):
                pass
        class Button:
            pass
        class TextInput:
            def __init__(self, *args, **kwargs):
                self.value = ""
                self.label = kwargs.get("label")
        @staticmethod
        def button(*args, **kwargs):
            def deco(func):
                return func
            return deco

    class DummyDiscord:
        Intents = DummyIntents
        ui = DummyUI
        Interaction = object
        ButtonStyle = type("ButtonStyle", (), {"primary": 1})

    discord = DummyDiscord()
    app_commands = DummyAppCommands()
    commands = None

# ==========================================
# Bot初期化
# ==========================================
TOKEN = os.getenv("DISCORD_TOKEN")
app = Flask(__name__)

@app.route("/")
def health():
    return "Bot is running"

if commands is None:
    class DummyBot:
        def __init__(self, *args, **kwargs):
            self.tree = self
        def command(self, *args, **kwargs):
            def deco(func):
                return func
            return deco
        def event(self, *args, **kwargs):
            def deco(func):
                return func
            return deco
        async def sync(self):
            pass
        def run(self, *args, **kwargs):
            pass
    bot = DummyBot()
else:
    # --- 🛠️ インテント設定の修正と追加 ------------------
    intents = discord.Intents.default()
    intents.members = True          # サーバーメンバーのステータス取得用
    intents.message_content = True  # 👈 【重要】メッセージ内容の読み取りを許可して警告を消す

    # プレフィックスコマンド「?」とスラッシュコマンドの両方を main 側で定義
    bot = commands.Bot(command_prefix=["/", "?"], intents=intents)
    # --------------------------------------------------

# ==========================================
# JSON 永続化データ管理
# ==========================================
DATA_FILE = "trains.json"
USAGE_FILE = "usage.json"

def load_trains():
    if not os.path.exists(DATA_FILE):
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump({}, f)
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_trains(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def load_usage_data():
    if not os.path.exists(USAGE_FILE):
        return {}
    try:
        with open(USAGE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}

def save_usage_data(data):
    try:
        with open(USAGE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except OSError:
        pass

# ==========================================
# 権限・クールダウン設定
# ==========================================
COMMAND_ROLE_ID = 1510405214811852900
ADMIN_ROLE_ID = 1510021467167789104
DEFAULT_ROUTE_NAME = "尾羽急本線"

async def check_role(interaction: discord.Interaction) -> bool:
    if not any(role.id == COMMAND_ROLE_ID for role in interaction.user.roles):
        await interaction.response.send_message("このコマンドを使う権限がありません。", ephemeral=True)
        return False
    return True

COMMAND_RULES = {
    "create": {
        "unlimited_roles": [1511882841997185064],
        "limited_roles": [1510021467155202057],
        "window_sec": 12 * 3600,
        "limit": 4
    },
    "create_emp": {
        "unlimited_roles": [1510405214811852900],
        "limited_roles": [1510021467167789097, 1511882841997185064],
        "window_sec": 24 * 3600,
        "limit": 5
    },
    "create_man": {
        "unlimited_roles": [1511882841997185064],
        "limited_roles": [1510405214811852900],
        "window_sec": 24 * 3600,
        "limit": 4
    },
    "create_auto": {
        "unlimited_roles": [1511882841997185064],
        "limited_roles": [1510405214811852900],
        "window_sec": 24 * 3600,
        "limit": 4
    }
}

def format_remaining_time(seconds):
    if seconds <= 0:
        return "0時間0分"
    hours = seconds // 3600
    minutes = (seconds % 3600 + 59) // 60
    if minutes >= 60:
        hours += 1
        minutes -= 60
    return f"{hours}時間{minutes}分"

async def check_command_permission(interaction: discord.Interaction, command_name: str) -> bool:
    rules = COMMAND_RULES.get(command_name)
    if rules is None:
        await interaction.response.send_message("このコマンドを使用する権限がありません。", ephemeral=True)
        return False

    user_roles = [getattr(role, "id", None) for role in getattr(interaction.user, "roles", [])]
    if ADMIN_ROLE_ID in user_roles:
        return True
    if any(role_id in rules["unlimited_roles"] for role_id in user_roles):
        return True
    if not any(role_id in rules["limited_roles"] for role_id in user_roles):
        await interaction.response.send_message("このコマンドを使用する権限がありません。", ephemeral=True)
        return False

    user_id = str(interaction.user.id)
    now = int(time.time())
    usage_data = load_usage_data()
    user_usage = usage_data.setdefault(user_id, {})
    timestamps = user_usage.setdefault(command_name, [])
    window_start = now - rules["window_sec"]
    timestamps = [ts for ts in timestamps if ts > window_start]

    if len(timestamps) >= rules["limit"]:
        earliest = min(timestamps)
        remaining = earliest + rules["window_sec"] - now
        await interaction.response.send_message(f"クールダウン中です。\n\nあと {format_remaining_time(remaining)}後に利用できます。", ephemeral=True)
        user_usage[command_name] = timestamps
        save_usage_data(usage_data)
        return False

    timestamps.append(now)
    user_usage[command_name] = timestamps
    usage_data[user_id] = user_usage
    save_usage_data(usage_data)
    return True

# ==========================================
# 鉄道データ (路線・駅・所要時間)
# =