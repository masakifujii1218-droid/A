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
    intents = discord.Intents.default()
    intents.members = True
    bot = commands.Bot(command_prefix="/", intents=intents)

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
            departure = arrival + timedelta(seconds=30)
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
    station_path, error =