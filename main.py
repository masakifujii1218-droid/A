from datetime import datetime, timedelta
import json
import os
import random
import threading
import time
import sub  # 👈 【超重要】上から7行目あたりに、この1行が絶対に必要です！

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
    from discord.ext import commands, tasks  # 👈 tasks を追加して定時処理を可能に
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
    
    # ダミーのtasksクラス
    class DummyTasks:
        @staticmethod
        def loop(*args, **kwargs):
            def deco(func):
                class DummyLoop:
                    def start(self): pass
                    def is_running(self): return False
                return DummyLoop()
            return deco
    tasks = DummyTasks()

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
    bot = commands.Bot(command_prefix="?", intents=intents)
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
# ==========================================
ROUTE_STATIONS = {
    "尾羽急本線": ["尾羽原", "井口", "梅郷", "雲中", "安越", "十川", "千峰", "南雲谷", "雲谷", "長峰", "西高徳", "高徳", "明神前", "舞子台", "紀田", "穂", "瀬舞", "余美", "千鳥"],
    "空港線": ["尾羽原", "井口", "梅郷", "雲中", "安越", "十川", "千峰", "南雲谷", "雲谷", "長峰", "西高徳", "高徳", "新高徳", "整備場", "空港"],
    "井問線": ["安越", "雲中", "梅郷", "井口", "上井口", "参田町", "東本郷", "本郷", "西問屋町", "問屋町", "千鳥"],
    "舞山線": ["舞山", "新舞山", "安小", "鳴田", "芽蒲", "池ノ上", "赤川", "那津", "西堀理", "堀理", "山谷", "大日古部", "中台", "輪厚"]
}

STOP_TIME = 30  # 停車時間は元の30秒を維持
TURNBACK_MINUTES = 5
MIN_HEADWAY = 2

LOCAL = {
    ("尾羽原", "井口"): 60, ("井口", "梅郷"): 60, ("梅郷", "雲中"): 30, ("雲中", "安越"): 60,
    ("安越", "十川"): 60, ("十川", "千峰"): 90, ("千峰", "南雲谷"): 80, ("南雲谷", "雲谷"): 120,
    ("雲谷", "長峰"): 75, ("長峰", "西高徳"): 90, ("西高徳", "高徳"): 90, ("高徳", "明神前"): 120,
    ("明神前", "舞子台"): 100, ("舞子台", "紀田"): 100, ("紀田", "穂"): 90, ("穂", "瀬舞"): 90,
    ("瀬舞", "余美"): 90, ("余美", "千鳥"): 90
}
EXPRESS = {
    ("尾羽原", "井口"): 85, ("井口", "安越"): 85, ("安越", "雲谷"): 180, ("雲谷", "高徳"): 140,
    ("高徳", "紀田"): 180, ("紀田", "千鳥"): 120
}
SEMI_EXPRESS = {
    ("尾羽原", "井口"): 90, ("井口", "雲中"): 120, ("雲中", "安越"): 60, ("安越", "千峰"): 120,
    ("千峰", "雲谷"): 150, ("雲谷", "長峰"): 120, ("長峰", "高徳"): 150, ("高徳", "舞子台"): 180,
    ("舞子台", "紀田"): 120, ("紀田", "千鳥"): 180
}
RAPID = {
    ("尾羽原", "井口"): 60, ("井口", "雲中"): 90, ("雲中", "安越"): 60, ("安越", "千峰"): 120,
    ("千峰", "雲谷"): 180, ("雲谷", "長峰"): 75, ("長峰", "西高徳"): 90, ("西高徳", "高徳"): 90,
    ("高徳", "明神前"): 120, ("明神前", "舞子台"): 100, ("舞子台", "紀田"): 100, ("紀田", "穂"): 90,
    ("穂", "瀬舞"): 90, ("瀬舞", "余美"): 90, ("余美", "千鳥"): 90
}
RAPID_EXPRESS = {
    ("尾羽原", "高徳"): 410, ("高徳", "紀田"): 180, ("紀田", "千鳥"): 120
}
IDEMON_LOCAL = {
    ("安越", "雲中"): 60, ("雲中", "梅郷"): 60, ("梅郷", "井口"): 60, ("井口", "上井口"): 90,
    ("上井口", "参田町"): 90, ("参田町", "東本郷"): 60, ("東本郷", "本郷"): 60, ("本郷", "西問屋町"): 80,
    ("西問屋町", "問屋町"): 110, ("問屋町", "千鳥"): 110
}
IDEMON_RAPID = {
    ("安越", "雲中"): 60, ("雲中", "井口"): 90, ("井口", "参田町"): 150, ("参田町", "本郷"): 90,
    ("本郷", "問屋町"): 180, ("問屋町", "千鳥"): 110
}
IDEMON_EXPRESS = {
    ("安越", "井口"): 120, ("井口", "本郷"): 240, ("本郷", "千鳥"): 240
}
SECTION_EXPRESS = {
    ("尾羽原", "井口"): 90, ("井口", "安越"): 120, ("安越", "雲谷"): 210, ("雲谷", "高徳"): 180,
    ("高徳", "明神前"): 150, ("明神前", "舞子台"): 120, ("舞子台", "紀田"): 90, ("紀田", "穂"): 90,
    ("穂", "瀬舞"): 90, ("瀬舞", "余美"): 90, ("余美", "千鳥"): 90
}

# --- 舞山線データ（純粋追加分） ---
MAIYAMA_LOCAL = {
    ("舞山", "新舞山"): 65, ("新舞山", "安小"): 70, ("安小", "鳴田"): 65, ("鳴田", "芽蒲"): 95,
    ("芽蒲", "池ノ上"): 75, ("池ノ上", "赤川"): 65, ("赤川", "那津"): 70, ("那津", "西堀理"): 60,
    ("西堀理", "堀理"): 75, ("堀理", "山谷"): 100, ("山谷", "大日古部"): 90, ("大日古部", "中台"): 90,
    ("中台", "輪厚"): 60
}
MAIYAMA_RAPID = {
    ("舞山", "安小"): 180, ("安小", "鳴田"): 60, ("鳴田", "芽蒲"): 60, ("芽蒲", "池ノ上"): 60,
    ("池ノ上", "赤川"): 60, ("赤川", "那津"): 90, ("那津", "西堀理"): 60, ("西堀理", "堀理"): 90
}
MAIYAMA_EXPRESS = {
    ("堀理", "那津"): 90, ("那津", "安小"): 90, ("安小", "舞山"): 210
}

ROUTE_TRAIN_TYPES = {
    "尾羽急本線": {"普通": LOCAL, "準急": SEMI_EXPRESS, "区間急行": SECTION_EXPRESS, "快速": RAPID, "急行": EXPRESS, "快速急行": RAPID_EXPRESS},
    "空港線": {
        "普通": {("尾羽原", "井口"): 60, ("井口", "梅郷"): 60, ("梅郷", "雲中"): 30, ("雲中", "安越"): 60, ("安越", "十川"): 60, ("十川", "千峰"): 90, ("千峰", "南雲谷"): 80, ("南雲谷", "雲谷"): 120, ("雲谷", "長峰"): 75, ("長峰", "西高徳"): 90, ("西高徳", "高徳"): 90, ("高徳", "新高徳"): 120, ("新高徳", "整備場"): 120, ("整備場", "空港"): 120},
        "快速": {("尾羽原", "井口"): 60, ("井口", "雲中"): 90, ("雲中", "安越"): 60, ("安越", "千峰"): 120, ("千峰", "南雲谷"): 180, ("南雲谷", "雲谷"): 180, ("雲谷", "長峰"): 75, ("長峰", "西高徳"): 90, ("西高徳", "高徳"): 90, ("高徳", "新高徳"): 120, ("新高徳", "整備場"): 120, ("整備場", "空港"): 120},
        "空港急行": {("尾羽原", "高徳"): 410, ("高徳", "新高徳"): 90, ("新高徳", "整備場"): 90, ("整備場", "空港"): 90}
    },
    "井問線": {"普通": IDEMON_LOCAL, "快速": IDEMON_RAPID, "急行": IDEMON_EXPRESS},
    "舞山線": {"普通": MAIYAMA_LOCAL, "快速": MAIYAMA_RAPID, "特急": MAIYAMA_EXPRESS}
}

ROUTE_AVOID_STATIONS = {
    "尾羽急本線": ["尾羽原", "安越", "雲谷", "高徳", "紀田", "千鳥"],
    "空港線": ["尾羽原", "安越", "雲谷", "高徳", "空港"],
    "井問線": ["安越", "井口", "本郷", "千鳥"],
    "舞山線": ["舞山", "新舞山", "安小", "芽蒲", "那津", "堀理"]
}

# ==========================================
# ダイヤ計算ロジック・共通関数
# ==========================================
def get_stops(route_name, train_type):
    data = ROUTE_TRAIN_TYPES[route_name][train_type]
    stations = set()
    for a, b in data.keys():
        stations.add(a)
        stations.add(b)
    return stations

def round_time(dt):
    if dt.second == 0:
        return dt.replace(microsecond=0)
    if dt.second <= 30:
        return dt.replace(second=30, microsecond=0)
    return (dt + timedelta(minutes=1)).replace(second=0, microsecond=0)

def calculate_times(route_name, train_type, start_station, end_station, start_time):
    if route_name not in ROUTE_STATIONS:
        return None, "未実装の路線です"
    if train_type not in ROUTE_TRAIN_TYPES[route_name]:
        return None, "その種別はありません"

    data = ROUTE_TRAIN_TYPES[route_name][train_type]
    stations = ROUTE_STATIONS[route_name]

    if start_station not in stations: return None, "開始駅が存在しません"
    if end_station not in stations: return None, "終了駅が存在しません"

    stops = get_stops(route_name, train_type)
    if start_station not in stops: return None, "開始駅は停車駅ではありません"
    if end_station not in stops: return None, "終了駅は停車駅ではありません"

    start_index = stations.index(start_station)
    end_index = stations.index(end_station)

    if start_index <= end_index:
        full_path = stations[start_index:end_index + 1]
    else:
        full_path = list(reversed(stations[end_index:start_index + 1]))

    path = [station for station in full_path if station in stops]

    try:
        current = datetime.strptime(start_time, "%H:%M")
    except ValueError:
        return None, "時刻は HH:MM"

    result = []
    result.append(f"{path[0]} {current.strftime('%H:%M:%S')}発")

    for i in range(1, len(path)):
        prev = path[i - 1]
        now = path[i]
        travel = data.get((prev, now)) or data.get((now, prev))
        if travel is None:
            return None, "この列車はこの区間を走行しません"

        current += timedelta(seconds=travel)
        arrive = round_time(current)

        if now == path[-1]:
            result.append(f"{now} {arrive.strftime('%H:%M:%S')}着")
            current = arrive
        else:
            depart = arrive + timedelta(seconds=STOP_TIME)
            result.append(f"{now} {arrive.strftime('%H:%M:%S')}着 {depart.strftime('%H:%M:%S')}発")
            current = depart

    return result, None

def generate_formatted_timetable(route_name, train_type, start_station, end_station, start_time):
    def round_up_to_30_seconds(dt: datetime) -> datetime:
        if dt.second == 0 or dt.second == 30:
            return dt.replace(microsecond=0)
        if dt.second < 30:
            return dt.replace(second=30, microsecond=0)
        return (dt + timedelta(seconds=60 - dt.second)).replace(second=0, microsecond=0)

    if route_name not in ROUTE_STATIONS: return None, f"{route_name} は未実装の路線です"
    if train_type not in ROUTE_TRAIN_TYPES[route_name]: return None, f"{route_name} では {train_type} は使用できません"

    data = ROUTE_TRAIN_TYPES[route_name][train_type]
    route_stations = ROUTE_STATIONS[route_name]
    stops = [station for station in route_stations if any(station == a or station == b for a, b in data.keys())]

    if start_station not in route_stations: return None, "開始駅は路線上の駅ではありません"
    if end_station not in route_stations: return None, "終了駅は路線上の駅ではありません"
    if start_station not in stops: return None, "開始駅は停車駅ではありません"
    if end_station not in stops: return None, "終了駅は停車駅ではありません"

    start_idx = route_stations.index(start_station)
    end_idx = route_stations.index(end_station)

    if start_idx <= end_idx:
        full_path = route_stations[start_idx:end_idx + 1]
    else:
        full_path = list(reversed(route_stations[end_idx:start_idx + 1]))

    path = [station for station in full_path if station in stops]
    if not path or path[0] != start_station or path[-1] != end_station:
        return None, "その種別はこの区間を走行しません"

    try:
        current = datetime.strptime(start_time, "%H:%M").replace(second=0, microsecond=0)
    except ValueError:
        return None, "開始時間の形式は HH:MM です"

    lines = []
    lines.append(f"{path[0]} {current.strftime('%H:%M:%S')}発")

    for index in range(1, len(path)):
        prev_station = path[index - 1]
        station = path[index]
        travel_time = data.get((prev_station, station)) or data.get((station, prev_station))
        if travel_time is None: return None, "その種別はこの区間を走行しません"

        current += timedelta(seconds=travel_time)
        arrival = round_up_to_30_seconds(current)

        if station == path[-1]:
            lines.append(f"{station} {arrival.strftime('%H:%M:%S')}着")
            current = arrival
        else:
            departure = arrival + timedelta(seconds=STOP_TIME)
            lines.append(f"{station} {arrival.strftime('%H:%M:%S')}着 {departure.strftime('%H:%M:%S')}発")
            current = departure

    return lines, None

def build_station_path(route_name, start_station, end_station):
    if route_name not in ROUTE_STATIONS: return None, "未実装の路線です"
    stations = ROUTE_STATIONS[route_name]
    if start_station not in stations: return None, "開始駅が存在しません"
    if end_station not in stations: return None, "終了駅が存在しません"

    s = stations.index(start_station)
    e = stations.index(end_station)
    if s <= e: return stations[s:e + 1], None
    return list(reversed(stations[e:s + 1])), None

def get_available_train_types(route_name):
    return list(ROUTE_TRAIN_TYPES[route_name].keys())

def choose_best_route(candidates):
    if not candidates: return None
    ranked = []
    for route_name in candidates:
        stations = ROUTE_STATIONS[route_name]
        ranked.append((len(stations), route_name == DEFAULT_ROUTE_NAME, route_name))
    ranked.sort(key=lambda item: (item[0], item[1], item[2]))
    return ranked[0][2]

def detect_route_name(start_station, end_station, via_station=None):
    if via_station: via_station = via_station.strip() or None
    if via_station:
        routes_with_all = [r for r, s in ROUTE_STATIONS.items() if start_station in s and via_station in s and end_station in s]
        if routes_with_all: return choose_best_route(routes_with_all)
        routes_start_via = [r for r, s in ROUTE_STATIONS.items() if start_station in s and via_station in s]
        if routes_start_via: return choose_best_route(routes_start_via)
        routes_via_end = [r for r, s in ROUTE_STATIONS.items() if via_station in s and end_station in s]
        if routes_via_end: return choose_best_route(routes_via_end)

    candidates = [r for r, s in ROUTE_STATIONS.items() if start_station in s and end_station in s]
    if not candidates: return DEFAULT_ROUTE_NAME
    return choose_best_route(candidates)

def generate_auto_timetable(route_name, start_station, end_station, start_time, end_time, count):
    if count < 1: return None, "本数は1以上です"
    station_path, error = build_station_path(route_name, start_station, end_station)
    if error: return None, error

    try:
        start_dt = datetime.strptime(start_time, "%H:%M")
        end_dt = datetime.strptime(end_time, "%H:%M")
    except ValueError:
        return None, "時刻は HH:MM"

    start_min = start_dt.hour * 60 + start_dt.minute
    end_min = end_dt.hour * 60 + end_dt.minute
    if end_min < start_min: end_min += 24 * 60

    departures = []
    trains = []
    types = get_available_train_types(route_name)
    avoid_candidates = ROUTE_AVOID_STATIONS.get(route_name, [])

    for _ in range(count):
        train_type = random.choice(types)
        minute = random.randint(start_min, end_min)
        while any(abs(minute - x) < 2 for x in departures):
            minute += 2

        departures.append(minute)
        dep = (datetime(2000, 1, 1) + timedelta(minutes=minute)).strftime("%H:%M")

        timetable, error = calculate_times(route_name, train_type, start_station, end_station, dep)
        if error: continue

        avoid = None
        valid_candidates = [s for s in station_path[1:-1] if s in avoid_candidates]
        if valid_candidates: 
            avoid = random.choice(valid_candidates)

        trains.append({
            "route": route_name, "type": train_type, "departure": dep,
            "start": start_station, "end": end_station,
            "note": f"待避駅: {avoid}" if avoid else "待避駅:なし",
            "departure_minutes": minute, "timetable": timetable
        })

    trains.sort(key=lambda x: x["departure_minutes"])
    return trains, None

# ==========================================
# 運用・スケジューリングクラス
# ==========================================
class TrainFormation:
    def __init__(self, number: int, route_name: str, start_station: str, end_station: str, departure: datetime):
        self.number = number
        self.route = route_name
        self.start_station = start_station
        self.end_station = end_station
        self.current_station = start_station
        self.next_departure = departure
        self.direction = 0

    def reverse(self):
        self.direction = 1 - self.direction
        self.current_station = self.start_station if self.direction == 0 else self.end_station

    def get_start(self):
        return self.start_station if self.direction == 0 else self.end_station

    def get_end(self):
        return self.end_station if self.direction == 0 else self.start_station

used_departures = {}

def adjust_departure(station: str, depart: datetime):
    while True:
        key = (station, depart.strftime("%H:%M"))
        if key not in used_departures:
            used_departures[key] = True
            return depart
        depart += timedelta(minutes=MIN_HEADWAY)

# ==========================================
# Discord スラッシュコマンド & モーダル UI
# ==========================================
class NextCompositionView(discord.ui.View):
    def __init__(self, route_name: str, composition_index: int, total_compositions: int, all_trains_data: list, callback=None):
        super().__init__()
        self.route_name = route_name
        self.composition_index = composition_index
        self.total_compositions = total_compositions
        self.all_trains_data = all_trains_data
        self.callback = callback

    @discord.ui.button(label="次へ", style=discord.ButtonStyle.primary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TrainInfoModal(self.route_name, self.composition_index + 1, self.total_compositions, self.all_trains_data, self.callback))

class ManualNextCompositionView(discord.ui.View):
    def __init__(self, route_name: str, composition_index: int, total_compositions: int, all_trains_data: list, callback=None):
        super().__init__()
        self.route_name = route_name
        self.composition_index = composition_index
        self.total_compositions = total_compositions
        self.all_trains_data = all_trains_data
        self.callback = callback

    @discord.ui.button(label="次へ", style=discord.ButtonStyle.primary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ManualTrainInfoModal(self.route_name, self.composition_index + 1, self.total_compositions, self.all_trains_data, self.callback))

class TrainInfoModal(discord.ui.Modal):
    def __init__(self, route_name: str, composition_index: int, total_compositions: int, all_trains_data: list, callback=None):
        super().__init__(title=f"編成 {composition_index}/{total_compositions}")
        self.route_name = route_name
        self.composition_index = composition_index
        self.total_compositions = total_compositions
        self.all_trains_data = all_trains_data
        self.callback = callback

    train_type = discord.ui.TextInput(label="種別", placeholder="普通/快速/急行/準急/区間急行/快速急行/特急", required=True)
    departure_time = discord.ui.TextInput(label="始発時刻", placeholder="HH:MM", required=True)
    start_station = discord.ui.TextInput(label="開始駅", required=True)
    via_station = discord.ui.TextInput(label="経由地（任意）", required=False)
    end_station = discord.ui.TextInput(label="終了駅", required=True)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        train_data = {
            "type": str(self.train_type), "departure": str(self.departure_time),
            "start": str(self.start_station), "via": str(self.via_station) if str(self.via_station).strip() else None,
            "end": str(self.end_station)
        }
        self.all_trains_data.append(train_data)

        if self.composition_index < self.total_compositions:
            view = NextCompositionView(self.route_name, self.composition_index, self.total_compositions, self.all_trains_data, self.callback)
            await interaction.response.send_message(f"編成 {self.composition_index} を記録しました\n次へボタンで編成 {self.composition_index + 1} を入力してください", view=view, ephemeral=True)
        else:
            await interaction.response.defer()
            if self.callback:
                await self.callback(interaction, self.route_name, self.all_trains_data)
            else:
                await interaction.followup.send(f"全 {self.composition_index} 編成を記録しました", ephemeral=True)

class ManualTrainInfoModal(discord.ui.Modal):
    def __init__(self, route_name: str, composition_index: int, total_compositions: int, all_trains_data: list, callback=None):
        super().__init__(title=f"編成 {composition_index}/{total_compositions}")
        self.route_name = route_name
        self.composition_index = composition_index
        self.total_compositions = total_compositions
        self.all_trains_data = all_trains_data
        self.callback = callback

    train_type = discord.ui.TextInput(label="種別", placeholder="普通/快速/急行/準急/区間急行/快速急行/特急", required=True)
    departure_time = discord.ui.TextInput(label="始発時刻", placeholder="HH:MM", required=True)
    start_station = discord.ui.TextInput(label="開始駅", required=True)
    via_station = discord.ui.TextInput(label="経由地（任意）", required=False)
    end_station = discord.ui.TextInput(label="終了駅", required=True)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        train_data = {
            "type": str(self.train_type), "departure": str(self.departure_time),
            "start": str(self.start_station), "via": str(self.via_station) if str(self.via_station).strip() else None,
            "end": str(self.end_station)
        }
        self.all_trains_data.append(train_data)

        if self.composition_index < self.total_compositions:
            view = ManualNextCompositionView(self.route_name, self.composition_index, self.total_compositions, self.all_trains_data, self.callback)
            await interaction.response.send_message(f"編成 {self.composition_index} を記録しました\n次へボタンで編成 {self.composition_index + 1} を入力してください", view=view, ephemeral=True)
        else:
            await interaction.response.defer()
            if self.callback:
                await self.callback(interaction, self.route_name, self.all_trains_data)
            else:
                await interaction.followup.send(f"全 {self.composition_index} 編成を記録しました", ephemeral=True)

@bot.tree.command(name="create-auto", description="自動ダイヤ作成")
async def create_auto(interaction: discord.Interaction, 開始駅: str, 終了駅: str, 経由地: str = None, *, 開始時刻: str, 終了時刻: str, 本数: int):
    if not await check_command_permission(interaction, "create_auto"): return
    route_name = detect_route_name(開始駅, 終了駅, 経由地)
    results, error = generate_auto_timetable(route_name, 開始駅, 終了駅, 開始時刻, 終了時刻, 本数)
    if error:
        await interaction.response.send_message(error, ephemeral=True)
        return

    lines = [f"【自動ダイヤ】{route_name} {開始駅}→{終了駅}"]
    for idx, train in enumerate(results, 1):
        lines.append(f"編成{idx}: {train['type']} {train['departure']}発")
        lines.append(f"  {train['note']}")
        lines.extend(f"  {line}" for line in train["timetable"])
        lines.append("")
    await interaction.response.send_message("\n".join(lines), ephemeral=True)

@app_commands.choices(
    種別=[
        app_commands.Choice(name="普通", value="普通"), app_commands.Choice(name="準急", value="準急"),
        app_commands.Choice(name="区間急行", value="区間急行"), app_commands.Choice(name="快速", value="快速"),
        app_commands.Choice(name="急行", value="急行"), app_commands.Choice(name="快速急行", value="快速急行"),
        app_commands.Choice(name="空港急行", value="空港急行"), app_commands.Choice(name="特急", value="特急")
    ]
)
@bot.tree.command(name="create", description="ダイヤ作成")
async def create(interaction: discord.Interaction, 種別: app_commands.Choice[str], 開始駅: str, 終了駅: str, 経由地: str = None, 開始時間: str = None):
    if not await check_command_permission(interaction, "create"): return
    route_name = detect_route_name(開始駅, 終了駅, 経由地)
    train_type = 種別.value

    if not 開始時間:
        await interaction.response.send_message("開始時間の形式は HH:MM です。", ephemeral=True)
        return

    lines, error = generate_formatted_timetable(route_name, train_type, 開始駅, 終了駅, 開始時間)
    if error:
        await interaction.response.send_message(error, ephemeral=True)
        return

    output = [f"【{train_type}】"]
    output.extend(lines)
    await interaction.response.send_message("\n".join(output))

@app_commands.choices(
    編成数=[
        app_commands.Choice(name="1編成", value=1), app_commands.Choice(name="2編成", value=2),
        app_commands.Choice(name="3編成", value=3), app_commands.Choice(name="4編成", value=4),
        app_commands.Choice(name="5編成", value=5)
    ]
)
@bot.tree.command(name="create-emp", description="最大5編成列車作成（フォーム入力）")
async def create_emp(interaction: discord.Interaction, 編成数: int):
    if not await check_command_permission(interaction, "create_emp"): return
    route_name = DEFAULT_ROUTE_NAME
    if route_name not in ROUTE_STATIONS:
        await interaction.response.send_message(f"{route_name} は未実装の路線です", ephemeral=True)
        return

    async def generate_emp_timetable(interaction: discord.Interaction, route_name: str, all_trains_data: list):
        messages = []
        for idx, train_data in enumerate(all_trains_data, 1):
            train_type = train_data["type"]
            departure = train_data["departure"]
            start_station = train_data["start"]
            via_station = train_data.get("via")
            end_station = train_data["end"]
            r_name = detect_route_name(start_station, end_station, via_station)
            
            timetable, error = generate_formatted_timetable(r_name, train_type, start_station, end_station, departure)
            if error:
                messages.append(f"❌ 編成{idx}: {error}")
            else:
                messages.append(f"✅ 編成{idx}: {train_type}")
                messages.extend(timetable)
                messages.append("")
        await interaction.followup.send("\n".join(messages), ephemeral=True)

    await interaction.response.send_modal(TrainInfoModal(route_name, 1, 編成数, [], generate_emp_timetable))

# ==========================================
# 🔄 Render再起動対策（1時間ごとの同期ループ）
# ==========================================
@tasks.loop(hours=1)
async def auto_backup_loop():
    try:
        if hasattr(sub, "sync_data"):
            await sub.sync_data(bot)
            print("【Render対策】1時間ごとの自動同期を正常に実行しました。")
    except Exception as e:
        print(f"【Render対策】自動同期中にエラーが発生しました: {e}")

# ==========================================
# システム起動処理
# ==========================================
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"{bot.user} でログインしました")
    
    # 🔄 起動時（再起動後）のデータ自動復元処理
    try:
        if hasattr(sub, "restore_data"):
            await sub.restore_data(bot)
            print("【Render対策】再起動前のデータをDiscordサーバーから自動復元しました！")
    except Exception as e:
        print(f"【Render対策】データ復元中にエラーが発生しました: {e}")
        
    # 🔄 自動バックアップループの開始
    if commands is not None and not auto_backup_loop.is_running():
        auto_backup_loop.start()
        print("【Render対策】1時間ごとの自動同期ループを開始しました。")

def start_web_server():
    port = int(os.environ.get("PORT", "5000"))
    print(f"Starting Flask on port {port}")
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

if __name__ == "__main__":
    print("Main started")

    # Flaskを別スレッドで起動
    web_thread = threading.Thread(target=start_web_server, daemon=True)
    web_thread.start()
    print("Web thread started")

    # 🔗 sub.py のModmail機能を完全に合流・起動させる
    try:
        import sub
        sub.setup_admin_commands(bot)  # sub.pyの眠っていた機能を起こします
        print("Modmail (sub.py) のイベントとコマンドを完全に読み込みました！")
    except ImportError:
        print("警告: sub.py が見つかりません。Modmail機能はスキップされます。")
    except Exception as e:
        print(f"sub.py の読み込み中にエラーが発生しました: {e}")

    # Discord Botの起動
    if TOKEN:
        bot.run(TOKEN)