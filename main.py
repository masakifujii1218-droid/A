from datetime import datetime, timedelta
import json
import os
import random
import threading
import time
import asyncio
import sys

# 🛠️ 新しいシステム（sub.py）をインポート
import sub

# 🛠️ 自己推薦システム（Quiz.py）をインポート
from quiz import load_config_from_discord, setup_quiz_commands

# 🛠️ ミニゲームシステム（game.py）をインポート【追加】
import game

# ==========================================
# Flask (RenderやUptimeRobot等の死活監視用)
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
    print("警告: flask がインストールされていないため、ダミーを使用します。")

app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is running"

# Renderのヘルスチェック用に追加
@app.route("/health")
def health():
    return "OK", 200

def run_flask():
    app.run(host="0.0.0.0", port=8080)

def keep_alive():
    t = threading.Thread(target=run_flask, daemon=True)
    t.start()

# ==========================================
# Discord
# ==========================================
import discord
from discord.ext import commands
from discord import app_commands

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# 🛠️ Quiz.py のテキストコマンド (!recommendadminpanel, !recommendpanel) をBotに登録
setup_quiz_commands(bot)

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
        await interaction.response.send_message(f"🚫 クールダウン中です。\n\nあと **{format_remaining_time(remaining)}** 後に利用できます。\n💡 `/quiz` に正解すると、制限をリセットできるチャンスがあります！", ephemeral=True)
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
# ==========================================
ROUTE_STATIONS = {
    "尾羽急本線": ["尾羽原", "井口", "梅郷", "雲中", "安越", "十川", "千峰", "南雲谷", "雲谷", "長峰", "西高徳", "高徳", "明神前", "舞子台", "紀田", "穂", "瀬舞", "余美", "千鳥"],
    "空港線": ["尾羽原", "井口", "梅郷", "雲中", "安越", "十川", "千峰", "南雲谷", "雲谷", "長峰", "西高徳", "高徳", "新高徳", "整備場", "空港"],
    "井問線": ["安越", "雲中", "梅郷", "井口", "上井口", "参田町", "東本郷", "本郷", "西問屋町", "問屋町", "千鳥"]
}

STOP_TIME = 30
TURNBACK_MINUTES = 5
MIN_HEADWAY = 2

LOCAL = {("尾羽原", "井口"): 60, ("井口", "梅郷"): 60, ("梅郷", "雲中"): 30, ("雲中", "安越"): 60, ("安越", "十川"): 60, ("十川", "千峰"): 90, ("千峰", "南雲谷"): 80, ("南雲谷", "雲谷"): 120, ("雲谷", "長峰"): 75, ("長峰", "西高徳"): 90, ("西高徳", "高徳"): 90, ("高徳", "明神前"): 120, ("明神前", "舞子台"): 100, ("舞子台", "紀田"): 100, ("紀田", "穂"): 90, ("穂", "瀬舞"): 90, ("瀬舞", "余美"): 90, ("余美", "千鳥"): 90}
EXPRESS = {("尾羽原", "井口"): 85, ("井口", "安越"): 85, ("安越", "雲谷"): 180, ("雲谷", "高徳"): 140, ("高徳", "紀田"): 180, ("紀田", "千鳥"): 120}
SEMI_EXPRESS = {("尾羽原", "井口"): 90, ("井口", "雲中"): 120, ("雲中", "安越"): 60, ("安越", "千峰"): 120, ("千峰", "雲谷"): 150, ("雲谷", "長峰"): 120, ("長峰", "高徳"): 150, ("高徳", "舞子台"): 180, ("舞子台", "紀田"): 120, ("紀田", "千鳥"): 180}
RAPID = {("尾羽原", "井口"): 60, ("井口", "雲中"): 90, ("雲中", "安越"): 60, ("安越", "千峰"): 120, ("千峰", "雲谷"): 180, ("雲谷", "長峰"): 75, ("長峰", "西高徳"): 90, ("西高徳", "高徳"): 90, ("高徳", "明神前"): 120, ("明神前", "舞子台"): 100, ("舞子台", "紀田"): 100, ("紀田", "穂"): 90, ("穂", "瀬舞"): 90, ("瀬舞", "余美"): 90, ("余美", "千鳥"): 90}
RAPID_EXPRESS = {("尾羽原", "高徳"): 410, ("高徳", "紀田"): 180, ("紀田", "千鳥"): 120}
IDEMON_LOCAL = {("安越", "雲中"): 60, ("雲中", "梅郷"): 60, ("梅郷", "井口"): 60, ("井口", "上井口"): 90, ("上井口", "参田町"): 90, ("参田町", "東本郷"): 60, ("東本郷", "本郷"): 60, ("本郷", "西問屋町"): 80, ("西問屋町", "問屋町"): 110, ("問屋町", "千鳥"): 110}
IDEMON_RAPID = {("安越", "雲中"): 60, ("雲中", "井口"): 90, ("井口", "参田町"): 150, ("参田町", "本郷"): 90, ("本郷", "問屋町"): 180, ("問屋町", "千鳥"): 110}
IDEMON_EXPRESS = {("安越", "井口"): 120, ("井口", "本郷"): 240, ("本郷", "千鳥"): 240}
SECTION_EXPRESS = {("尾羽原", "井口"): 90, ("井口", "安越"): 120, ("安越", "雲谷"): 210, ("雲谷", "高徳"): 180, ("高徳", "明神前"): 150, ("明神前", "舞子台"): 120, ("舞子台", "紀田"): 90, ("紀田", "穂"): 90, ("穂", "瀬舞"): 90, ("瀬舞", "余美"): 90, ("余美", "千鳥"): 90}

ROUTE_TRAIN_TYPES = {
    "尾羽急本線": {"普通": LOCAL, "準急": SEMI_EXPRESS, "区間急行": SECTION_EXPRESS, "快速": RAPID, "急行": EXPRESS, "快速急行": RAPID_EXPRESS},
    "空港線": {
        "普通": {("尾羽原", "井口"): 60, ("井口", "梅郷"): 60, ("梅郷", "雲中"): 30, ("雲中", "安越"): 60, ("安越", "十川"): 60, ("十川", "千峰"): 90, ("千峰", "南雲谷"): 80, ("南雲谷", "雲谷"): 120, ("雲谷", "長峰"): 75, ("長峰", "西高徳"): 90, ("西高徳", "高徳"): 90, ("高徳", "新高徳"): 120, ("新高徳", "整備場"): 120, ("整備場", "空港"): 120},
        "快速": {("尾羽原", "井口"): 60, ("井口", "雲中"): 90, ("雲中", "安越"): 60, ("安越", "千峰"): 120, ("千峰", "南雲谷"): 180, ("南雲谷", "雲谷"): 180, ("雲谷", "長峰"): 75, ("長峰", "西高徳"): 90, ("西高徳", "高徳"): 90, ("高徳", "新高徳"): 120, ("新高徳", "整備場"): 120, ("整備場", "空港"): 120},
        "空港急行": {("尾羽原", "高徳"): 410, ("高徳", "新高徳"): 90, ("新高徳", "整備場"): 90, ("整備場", "空港"): 90}
    },
    "井問線": {"普通": IDEMON_LOCAL, "快速": IDEMON_RAPID, "急行": IDEMON_EXPRESS}
}

# ==========================================
# クイズデータ (尾羽急鉄道クイズ)
# ==========================================
QUIZ_LIST = [
    {
        "question": "尾羽急本線の「快速急行」が、尾羽原を出発した後に最初に停車する駅はどこ？",
        "choices": ["井口", "安越", "高徳", "千峰"],
        "answer": "高徳"
    },
    {
        "question": "空港線の終着駅はどこ？",
        "choices": ["空港", "新高徳", "整備場", "千鳥"],
        "answer": "空港"
    },
    {
        "question": "井問線の「普通」列車で、安越から雲中までの所要時間は何秒？",
        "choices": ["30秒", "60秒", "90秒", "120秒"],
        "answer": "60秒"
    },
    {
        "question": "尾羽急本線において、区間急行が停車しない駅は次のうちどれ？",
        "choices": ["南雲谷", "舞子台", "千鳥", "紀田"],
        "answer": "南雲谷"
    }
]

# ==========================================
# ダイヤ計算ロジック
# ==========================================
def get_stops(route_name, train_type):
    data = ROUTE_TRAIN_TYPES[route_name][train_type]
    stations = set()
    for a, b in data.keys():
        stations.add(a)
        stations.add(b)
    return stations

def calculate_times(route_name, train_type, start_station, end_station, start_time_str):
    if route_name not in ROUTE_STATIONS:
        return None, "未実装の路線です"
    if train_type not in ROUTE_TRAIN_TYPES[route_name]:
        return None, "その種別はありません"

    stations = ROUTE_STATIONS[route_name]
    if start_station not in stations: 
        return None, "開始駅が存在しません"
    if end_station not in stations: 
        return None, "終了駅が存在しません"

    stops = get_stops(route_name, train_type)
    if start_station not in stops: 
        return None, "開始駅は停車駅ではありません"
    if end_station not in stops: 
        return None, "終了駅は停車駅ではありません"

    try:
        base_time = datetime.strptime(start_time_str, "%H:%M")
    except ValueError:
        return None, "時刻の形式が不正です (HH:MM で指定してください)"

    start_idx = stations.index(start_station)
    end_idx = stations.index(end_station)
    is_down = start_idx < end_idx

    current_idx = start_idx
    current_time = base_time
    timetable = []

    timetable.append({
        "station": start_station,
        "arr": "--:--",
        "dep": current_time.strftime("%H:%M")
    })

    route_data = ROUTE_TRAIN_TYPES[route_name][train_type]

    while current_idx != end_idx:
        next_idx = current_idx + 1 if is_down else current_idx - 1
        curr_st = stations[current_idx]
        next_st = stations[next_idx]

        section = (curr_st, next_st) if is_down else (next_st, curr_st)
        if section in route_data:
            travel_time_sec = route_data[section]
            current_time += timedelta(seconds=travel_time_sec)
            
            if next_st in stops:
                arr_time = current_time
                if next_idx == end_idx:
                    timetable.append({
                        "station": next_st,
                        "arr": arr_time.strftime("%H:%M"),
                        "dep": "--:--"
                    })
                else:
                    dep_time = arr_time + timedelta(seconds=STOP_TIME)
                    timetable.append({
                        "station": next_st,
                        "arr": arr_time.strftime("%H:%M"),
                        "dep": dep_time.strftime("%H:%M")
                    })
                    current_time = dep_time
        
        current_idx = next_idx

    return timetable, None

# ==========================================
# クイズ UI (インタラクティブボタン)
# ==========================================
class QuizView(discord.ui.View):
    def __init__(self, quiz_data, user_id):
        super().__init__(timeout=60.0)
        self.quiz_data = quiz_data
        self.user_id = user_id

        # 4つの選択肢に対応するボタンを動的に配置
        for choice in self.quiz_data["choices"]:
            button = discord.ui.Button(label=choice, style=discord.ButtonStyle.primary, custom_id=choice)
            button.callback = self.on_button_click
            self.add_item(button)

    async def on_button_click(self, interaction: discord.Interaction):
        # 回答者本人以外の入力を無視
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("これはあなたのクイズではありません！", ephemeral=True)
            return

        selected_answer = interaction.data["custom_id"]
        correct_answer = self.quiz_data["answer"]

        # 全てのボタンを無効化
        for item in self.children:
            item.disabled = True

        if selected_answer == correct_answer:
            # 【クールダウンリセット連携】
            usage_data = load_usage_data()
            user_id_str = str(interaction.user.id)
            if user_id_str in usage_data:
                # create コマンドの履歴（クールダウン）を完全にリセット
                if "create" in usage_data[user_id_str]:
                    usage_data[user_id_str]["create"] = []
                save_usage_data(usage_data)
                benefit_text = "\n🎉 **ご褒美:** `/create` のクールダウン制限が完全にリセットされました！今すぐ作成可能です！"
            else:
                benefit_text = "\n🎉 **ご褒美:** クールダウンは元々ありませんが、これでいつでも作成可能です！"

            embed = discord.Embed(
                title="🟢 正解！",
                description=f"お見事！正解は **{correct_answer}** です！{benefit_text}",
                color=discord.Color.green()
            )
        else:
            embed = discord.Embed(
                title="🔴 不正解...",
                description=f"残念！正解は **{correct_answer}** でした。また次回挑戦してください！",
                color=discord.Color.red()
            )

        await interaction.response.edit_message(embed=embed, view=self)
        self.stop()

# ==========================================
# スラッシュコマンドの実装 (/create & /quiz)
# ==========================================
@bot.tree.command(name="create", description="新しいダイヤを作成し、各駅の時刻表を出力します。")
@app_commands.describe(
    路線="ダイヤを作成する路線名",
    種別="列車の種別（普通、快速、急行など）",
    始発駅="列車の出発駅",
    終着駅="列車の終点駅",
    始発時刻="出発時刻 (例: 12:00)"
)
async def create_dia_command(
    interaction: discord.Interaction,
    路線: str,
    種別: str,
    始発駅: str,
    終着駅: str,
    始発時刻: str
):
    if not await check_command_permission(interaction, "create"):
        return

    timetable, error = calculate_times(路線, 種別, 始発駅, 終着駅, 始発時刻)
    if error:
        await interaction.response.send_message(f"❌ エラー: {error}", ephemeral=True)
        return

    embed = discord.Embed(
        title=f"🚆 ダイヤ作成結果 ({種別})",
        description=f"**路線:** {路線}\n**運行区間:** {始発駅} ➡ {終着駅}",
        color=discord.Color.green()
    )

    schedule_text = ""
    for stop in timetable:
        schedule_text += f"**{stop['station']}駅** - 着 {stop['arr']} / 発 {stop['dep']}\n"

    embed.add_field(name="時刻表", value=schedule_text, inline=False)
    
    train_data = load_trains()
    train_id = f"TRN-{random.randint(1000, 9999)}"
    train_data[train_id] = {
        "route": 路線,
        "type": 種別,
        "timetable": timetable,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    save_trains(train_data)

    embed.set_footer(text=f"管理ID: {train_id} | 設定者: {interaction.user.name}")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="quiz", description="尾羽急に関する鉄道クイズを出題します！正解するとダイヤ作成制限がリセットされます。")
async def quiz_command(interaction: discord.Interaction):
    quiz = random.choice(QUIZ_LIST)
    
    embed = discord.Embed(
        title="❓ 尾羽急 鉄道クイズ！",
        description=f"**問題:**\n{quiz['question']}\n\n下のボタンから正解を選択してください！",
        color=discord.Color.blue()
    )
    embed.set_footer(text="※制限時間 60秒 | 正解すると /create のクールダウンがリセットされます！")

    view = QuizView(quiz_data=quiz, user_id=interaction.user.id)
    await interaction.response.send_message(embed=embed, view=view)

# ==========================================
# 🛠️ BOT管理部専用 !botinfo コマンド
# ==========================================
import psutil

# 許可された管理部のロールIDリスト
ADMIN_ROLE_IDS = [1510021467167789104, 1528521149582151751]

# エラーログと起動時間・オンライン時間の初期化
error_logs = []
bot_start_time = time.time()
bot_last_online_time = time.time()

# 他の処理を邪魔しない独立したエラーキャッチ
@bot.event
async def on_error(event, *args, **kwargs):
    import traceback
    error_msg = traceback.format_exc().splitlines()[-1]
    current_t = time.strftime("%H:%M:%S", time.localtime())
    error_logs.append(f"[{current_t}] {error_msg}")
    if len(error_logs) > 3:
        error_logs.pop(0)

@bot.command(name="botinfo")
async def botinfo_command(ctx):
    # 1. 権限チェック（実行者のロールIDリスト内に許可されたロールIDが含まれているかチェック）
    user_role_ids = [role.id for role in getattr(ctx.author, "roles", [])]
    has_permission = any(role_id in ADMIN_ROLE_IDS for role_id in user_role_ids)

    if not has_permission:
        # ロールを持っていない場合は無視して処理終了
        return

    global bot_last_online_time
    bot_last_online_time = time.time()  # コマンドが実行できた＝オンラインなので時刻更新

    # 2. 各種ステータスの計算
    # Ping (応答速度)
    ping = round(bot.latency * 1000) if bot.latency is not None else 0
    
    # メモリ使用率 (Render無料枠 512MB基準)
    process = psutil.Process(os.getpid())
    mem_bytes = process.memory_info().rss
    mem_mb = round(mem_bytes / (1024 * 1024), 1)
    mem_percent = round((mem_mb / 512) * 100, 1)

    # 起動してからの経過時間
    uptime_seconds = int(time.time() - bot_start_time)
    hours, remainder = divmod(uptime_seconds, 3600)
    minutes, _ = divmod(remainder, 60)
    
    # 時刻のフォーマット化 (日本時間)
    start_str = time.strftime("%Y/%m/%d %H:%M", time.localtime(bot_start_time))
    online_str = time.strftime("%Y/%m/%d %H:%M:%S", time.localtime(bot_last_online_time))

    # 3. エラー表示の生成
    if error_logs:
        error_content = "\n".join([f"{i+1}. `{log}`" for i, log in enumerate(error_logs)])
    else:
        error_content = "なし"

    # 4. 埋め込みメッセージ（Embed）で出力
    embed = discord.Embed(title="🤖 Bot稼働状況", color=0x00ff00)
    embed.add_field(name="● 現在のステータス", value="正常稼働中", inline=False)
    embed.add_field(name="● Discord API接続状況", value="良好（Connected）\n*※ここが「切断（Disconnected）」ならゾンビ状態です*", inline=False)
    embed.add_field(name="● 応答速度 (Ping)", value=f"{ping} ms", inline=False)
    embed.add_field(name="● メモリ使用率", value=f"{mem_percent}% ({mem_mb}MB / 512MB)", inline=False)
    embed.add_field(name="● 本日のエラー発生数", value=f"{len(error_logs)} 件 ⚠️", inline=False)
    embed.add_field(name="🚨 直近のエラー内容（最新3件まで）", value=error_content, inline=False)
    embed.add_field(name="● 起動してから", value=f"{hours}時間 {minutes}分 経過\n*({start_str} 起動)*", inline=False)
    embed.add_field(name="● Bot最終オンライン時刻", value=f"{online_str} (リアルタイム)", inline=False)

    await ctx.send(embed=embed)

# ==========================================
# 🛠️ 指定ロール専用 !restart コマンド
# ==========================================
RESTART_ALLOWED_ROLE_IDS = [1528521149582151751, 1510405214811852900]

@bot.command(name="restart")
async def restart_command(ctx):
    # 権限チェック（実行者が指定されたロールのいずれかを持っているか）
    user_role_ids = [role.id for role in getattr(ctx.author, "roles", [])]
    has_permission = any(role_id in RESTART_ALLOWED_ROLE_IDS for role_id in user_role_ids)

    if not has_permission:
        # ロールを持っていない場合は無応答で終了
        return

    await ctx.send("🔄 **Botを再起動しています...**\n※自動再起動システムにより数秒〜数十秒で復帰します。")
    print(f"🔄 [再起動] {ctx.author} によって !restart が実行されました。")

    # BotをDiscordから正常ログアウト
    await bot.close()

    # プロセスを終了（Render等のホスティングサービスがこれを検知して自動再起動します）
    sys.exit(0)

# ==========================================
# 起動処理
# ==========================================
@bot.event
async def on_ready():
    print(f"ログインしました: {bot.user.name} (ID: {bot.user.id})")
    
    # ------------------------------------------
    # 🛠️ ここから sub.py (ポイント・チケット) のドッキング処理
    # ------------------------------------------
    print("🔄 [起動処理] Discordから最新データベースの読み込みを開始します...")
    try:
        await sub.setup_sub_system(bot)
        print("✅ [起動処理] データベースの初期同期が完了しました。")
    except Exception as e:
        print(f"❌ [起動処理] データベース同期中にエラーが発生しました: {e}")

    print("⚙️ [起動処理] sub.py のスラッシュコマンドを登録中...")
    sub.setup_slash_commands(bot)
    # ------------------------------------------
    # 🛠️ ここまで
    # ------------------------------------------

    # ------------------------------------------
    # 🛠️ ここから Quiz.py (自己推薦設定データ) の復旧処理
    # ------------------------------------------
    print("🔄 [起動処理] Quiz.py の設定データをDiscordから復旧中...")
    try:
        await load_config_from_discord(bot)
        print("✅ [起動処理] Quiz.py のデータ復旧が完了しました。")
    except Exception as e:
        print(f"❌ [起動処理] Quiz.py データ復旧中にエラーが発生しました: {e}")
    # ------------------------------------------
    # 🛠️ ここまで
    # ------------------------------------------

    # ------------------------------------------
    # 🛠️ ここから game.py (ミニゲーム機能) の登録処理【追加】
    # ------------------------------------------
    print("🎮 [起動処理] game.py のミニゲームコマンドを登録中...")
    try:
        game.setup_game_commands(bot)
        print("✅ [起動処理] game.py のコマンド登録が完了しました。")
    except Exception as e:
        print(f"❌ [起動処理] game.py 登録中にエラーが発生しました: {e}")
    # ------------------------------------------
    # 🛠️ ここまで【追加】
    # ------------------------------------------

    # 🧹 重複防止：一旦古いコマンド設定をクリアしてから全体同期
    print("⚡ [起動処理] コマンドの重複をクリアして再同期中...")
    try:
        # 参加している各サーバーの個別（ギルド）コマンドを削除
        for guild in bot.guilds:
            bot.tree.clear_commands(guild=guild)
            await bot.tree.sync(guild=guild)

        # グローバル（全体）コマンドとして1つだけ同期
        synced = await bot.tree.sync()
        print(f"🚀 {len(synced)} 個のコマンドを同期しました。(重複解消済み)")
    except Exception as e:
        print(f"同期エラー: {e}")

if __name__ == "__main__":
    keep_alive()
    
    token = os.getenv("DISCORD_TOKEN") or os.getenv("DISCORD_BOT_TOKEN")
    if token:
        bot.run(token)
    else:
        print("エラー: 環境変数 'DISCORD_TOKEN' または 'DISCORD_BOT_TOKEN' が設定されていません。")
