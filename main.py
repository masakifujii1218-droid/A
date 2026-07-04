from datetime import datetime, timedelta
import json
import os
import random
import threading
import time

# ==========================
# Flask
# ==========================

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

# ==========================
# Discord
# ==========================

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

        @staticmethod
        def button(*args, **kwargs):
            def deco(func):
                return func
            return deco

    class DummyDiscord:

        Intents = DummyIntents
        ui = DummyUI
        Interaction = object

        ButtonStyle = type(
            "ButtonStyle",
            (),
            {
                "primary": 1
            }
        )

    discord = DummyDiscord()
    app_commands = DummyAppCommands()
    commands = None

# ==========================
# Bot
# ==========================

TOKEN = os.getenv("DISCORD_TOKEN")

app = Flask(__name__)

@app.route("/")
def health():
    return "Bot is running"

if commands is None:

    class DummyBot:

        def __init__(self):
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

    bot = commands.Bot(
        command_prefix="/",
        intents=intents
    )

# ==========================
# JSON
# ==========================

DATA_FILE = "trains.json"

def load_trains():

    if not os.path.exists(DATA_FILE):

        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump({}, f)

    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_trains(data):

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=4
        )

# ==========================
# 権限
# ==========================

COMMAND_ROLE_ID = 1510405214811852900

async def check_role(interaction):

    if not any(
        role.id == COMMAND_ROLE_ID
        for role in interaction.user.roles
    ):
        await interaction.response.send_message(
            "このコマンドを使う権限がありません。",
            ephemeral=True
        )
        return False

    return True
# ==========================================
# 路線
# ==========================================

ROUTE_STATIONS = {

    "尾羽急本線": [
        "尾羽原",
        "井口",
        "梅郷",
        "雲中",
        "安越",
        "十川",
        "千峰",
        "南雲谷",
        "雲谷",
        "長峰",
        "西高徳",
        "高徳",
        "明神前",
        "舞子台",
        "紀田",
        "穂",
        "瀬舞",
        "余美",
        "千鳥"
    ],

    "空港線": [
        "尾羽原",
        "井口",
        "梅郷",
        "雲中",
        "安越",
        "十川",
        "千峰",
        "南雲谷",
        "雲谷",
        "長峰",
        "西高徳",
        "高徳",
        "新高徳",
        "整備場",
        "空港"
    ]

}

# ==========================================
# 停車時間
# ==========================================

STOP_TIME = 30

# ==========================================
# 停車駅取得
# ==========================================

def get_stops(route_name, train_type):

    data = ROUTE_TRAIN_TYPES[route_name][train_type]

    stations = set()

    for a, b in data:

        stations.add(a)
        stations.add(b)

    return stations

# ==========================================
# 秒を30秒単位に丸める
# ==========================================

def round_time(dt):

    if dt.second == 0:

        return dt.replace(microsecond=0)

    if dt.second <= 30:

        return dt.replace(
            second=30,
            microsecond=0
        )

    return (
        dt +
        timedelta(minutes=1)
    ).replace(
        second=0,
        microsecond=0
    )

# ==========================================
# ダイヤ生成（完成版）
# ==========================================

def calculate_times(
    route_name,
    train_type,
    start_station,
    end_station,
    start_time
):

    if route_name not in ROUTE_STATIONS:
        return None, "未実装の路線です"

    if train_type not in ROUTE_TRAIN_TYPES[route_name]:
        return None, "その種別はありません"

    data = ROUTE_TRAIN_TYPES[route_name][train_type]

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

    start_index = stations.index(start_station)
    end_index = stations.index(end_station)

    if start_index <= end_index:

        full_path = stations[start_index:end_index + 1]

    else:

        full_path = list(
            reversed(
                stations[end_index:start_index + 1]
            )
        )

    path = []

    for station in full_path:

        if station in stops:

            path.append(station)

    try:

        current = datetime.strptime(
            start_time,
            "%H:%M"
        )

    except ValueError:

        return None, "時刻は HH:MM"

    result = []

    result.append(
        f"{path[0]} {current.strftime('%H:%M:%S')}発"
    )

    for i in range(1, len(path)):

        prev = path[i - 1]
        now = path[i]

        travel = (
            data.get((prev, now))
            or
            data.get((now, prev))
        )

        if travel is None:

            return None, "この列車はこの区間を走行しません"

        current += timedelta(seconds=travel)

        arrive = round_time(current)

        if now == path[-1]:

            result.append(
                f"{now} {arrive.strftime('%H:%M:%S')}着"
            )

            current = arrive

        else:

            depart = arrive + timedelta(
                seconds=STOP_TIME
            )

            result.append(
                f"{now} "
                f"{arrive.strftime('%H:%M:%S')}着 "
                f"{depart.strftime('%H:%M:%S')}発"
            )

            current = depart

    return result, None
# ==========================================
# 路線経路取得
# ==========================================

def build_station_path(route_name, start_station, end_station):

    if route_name not in ROUTE_STATIONS:
        return None, "未実装の路線です"

    stations = ROUTE_STATIONS[route_name]

    if start_station not in stations:
        return None, "開始駅が存在しません"

    if end_station not in stations:
        return None, "終了駅が存在しません"

    s = stations.index(start_station)
    e = stations.index(end_station)

    if s <= e:
        return stations[s:e + 1], None

    return list(reversed(stations[e:s + 1])), None


# ==========================================
# 種別一覧
# ==========================================

def get_available_train_types(route_name):

    return list(
        ROUTE_TRAIN_TYPES[route_name].keys()
    )


# ==========================================
# 自動ダイヤ生成
# ==========================================

def generate_auto_timetable(
    route_name,
    start_station,
    end_station,
    start_time,
    end_time,
    count
):

    if count < 1:
        return None, "本数は1以上です"

    station_path, error = build_station_path(
        route_name,
        start_station,
        end_station
    )

    if error:
        return None, error

    try:

        start_dt = datetime.strptime(
            start_time,
            "%H:%M"
        )

        end_dt = datetime.strptime(
            end_time,
            "%H:%M"
        )

    except ValueError:

        return None, "時刻は HH:MM"

    start_min = start_dt.hour * 60 + start_dt.minute
    end_min = end_dt.hour * 60 + end_dt.minute

    if end_min < start_min:
        end_min += 24 * 60

    departures = []

    trains = []

    types = get_available_train_types(route_name)

    for _ in range(count):

        train_type = random.choice(types)

        minute = random.randint(
            start_min,
            end_min
        )

        while any(
            abs(minute - x) < 2
            for x in departures
        ):
            minute += 2

        departures.append(minute)

        dep = (
            datetime(2000,1,1)
            + timedelta(minutes=minute)
        ).strftime("%H:%M")

        timetable, error = calculate_times(
            route_name,
            train_type,
            start_station,
            end_station,
            dep
        )

        if error:
            continue

        avoid = None

        candidates = [
            s
            for s in station_path[1:-1]
        ]

        if candidates:

            avoid = random.choice(
                candidates
            )

        trains.append({

            "route": route_name,

            "type": train_type,

            "departure": dep,

            "start": start_station,

            "end": end_station,

            "note":
                f"待避駅: {avoid}"
                if avoid
                else "待避駅:なし",

            "departure_minutes": minute,

            "timetable": timetable

        })

    trains.sort(
        key=lambda x:
        x["departure_minutes"]
    )

    return trains, None

# ==========================================
# 種別・運行データ
# ==========================================

LOCAL = {
    ("尾羽原", "井口"): 60,
    ("井口", "梅郷"): 60,
    ("梅郷", "雲中"): 30,
    ("雲中", "安越"): 60,
    ("安越", "十川"): 60,
    ("十川", "千峰"): 90,
    ("千峰", "南雲谷"): 80,
    ("南雲谷", "雲谷"): 120,
    ("雲谷", "長峰"): 75,
    ("長峰", "西高徳"): 90,
    ("西高徳", "高徳"): 90,
    ("高徳", "明神前"): 150,
    ("明神前", "舞子台"): 120,
    ("舞子台", "紀田"): 90,
    ("紀田", "穂"): 90,
    ("穂", "瀬舞"): 90,
    ("瀬舞", "余美"): 90,
    ("余美", "千鳥"): 90
}

SEMI_EXPRESS = {
    ("尾羽原", "井口"): 60,
    ("井口", "安越"): 120,
    ("安越", "雲谷"): 210,
    ("雲谷", "高徳"): 180,
    ("高徳", "明神前"): 150,
    ("明神前", "舞子台"): 120,
    ("舞子台", "紀田"): 90,
    ("紀田", "穂"): 90,
    ("穂", "瀬舞"): 90,
    ("瀬舞", "余美"): 90,
    ("余美", "千鳥"): 90
}

RAPID = {
    ("尾羽原", "井口"): 60,
    ("井口", "安越"): 120,
    ("安越", "雲谷"): 210,
    ("雲谷", "高徳"): 180,
    ("高徳", "明神前"): 150,
    ("明神前", "舞子台"): 120,
    ("舞子台", "紀田"): 90,
    ("紀田", "穂"): 90,
    ("穂", "瀬舞"): 90,
    ("瀬舞", "余美"): 90,
    ("余美", "千鳥"): 90
}

EXPRESS = {
    ("尾羽原", "高徳"): 410,
    ("高徳", "紀田"): 180,
    ("紀田", "千鳥"): 120
}

RAPID_EXPRESS = {
    ("尾羽原", "高徳"): 410,
    ("高徳", "紀田"): 180,
    ("紀田", "千鳥"): 120
}

SECTION_EXPRESS = {
    ("尾羽原", "井口"): 90,
    ("井口", "安越"): 120,
    ("安越", "雲谷"): 210,
    ("雲谷", "高徳"): 180,
    ("高徳", "明神前"): 150,
    ("明神前", "舞子台"): 120,
    ("舞子台", "紀田"): 90,
    ("紀田", "穂"): 90,
    ("穂", "瀬舞"): 90,
    ("瀬舞", "余美"): 90,
    ("余美", "千鳥"): 90
}

ROUTE_TRAIN_TYPES = {
    "尾羽急本線": {
        "普通": LOCAL,
        "準急": SEMI_EXPRESS,
        "区間急行": SECTION_EXPRESS,
        "快速": RAPID,
        "急行": EXPRESS,
        "快速急行": RAPID_EXPRESS
    },
    "空港線": {
        "普通": {
            ("尾羽原", "井口"): 60,
            ("井口", "梅郷"): 60,
            ("梅郷", "雲中"): 30,
            ("雲中", "安越"): 60,
            ("安越", "十川"): 60,
            ("十川", "千峰"): 90,
            ("千峰", "南雲谷"): 80,
            ("南雲谷", "雲谷"): 120,
            ("雲谷", "長峰"): 75,
            ("長峰", "西高徳"): 90,
            ("西高徳", "高徳"): 90,
            ("高徳", "新高徳"): 120,
            ("新高徳", "整備場"): 120,
            ("整備場", "空港"): 120
        },
        "快速": {
            ("尾羽原", "井口"): 60,
            ("井口", "雲中"): 90,
            ("雲中", "安越"): 60,
            ("安越", "千峰"): 120,
            ("千峰", "南雲谷"): 180,
            ("南雲谷", "雲谷"): 180,
            ("雲谷", "長峰"): 75,
            ("長峰", "西高徳"): 90,
            ("西高徳", "高徳"): 90,
            ("高徳", "新高徳"): 120,
            ("新高徳", "整備場"): 120,
            ("整備場", "空港"): 120
        },
        "空港急行": {
            ("尾羽原", "高徳"): 410,
            ("高徳", "新高徳"): 90,
            ("新高徳", "整備場"): 90,
            ("整備場", "空港"): 90
        }
    }
}

@app_commands.choices(
    路線名=[
        app_commands.Choice(name="尾羽急本線", value="尾羽急本線"),
        app_commands.Choice(name="空港線", value="空港線")
    ],
    種別=[
        app_commands.Choice(name="普通", value="普通"),
        app_commands.Choice(name="準急", value="準急"),
        app_commands.Choice(name="区間急行", value="区間急行"),
        app_commands.Choice(name="快速", value="快速"),
        app_commands.Choice(name="急行", value="急行"),
        app_commands.Choice(name="快速急行", value="快速急行"),
        app_commands.Choice(name="空港急行", value="空港急行")
    ]
)
@bot.tree.command(name="create", description="ダイヤ作成")
async def create(
    interaction: discord.Interaction,
    路線名: app_commands.Choice[str],
    種別: app_commands.Choice[str],
    開始時間: str,
    開始駅: str,
    終了駅: str
):
    if not await check_role(interaction):
        return

    route_name = 路線名.value
    train_type = 種別.value

    def round_up_to_30_seconds(dt: datetime) -> datetime:
        if dt.second == 0 or dt.second == 30:
            return dt.replace(microsecond=0)
        if dt.second < 30:
            return dt.replace(second=30, microsecond=0)
        return (dt + timedelta(seconds=60 - dt.second)).replace(second=0, microsecond=0)

    if route_name not in ROUTE_STATIONS:
        await interaction.response.send_message(
            f"{route_name} は未実装の路線です",
            ephemeral=True
        )
        return

    if train_type not in ROUTE_TRAIN_TYPES[route_name]:
        await interaction.response.send_message(
            f"{route_name} では {train_type} は使用できません",
            ephemeral=True
        )
        return

    data = ROUTE_TRAIN_TYPES[route_name][train_type]
    route_stations = ROUTE_STATIONS[route_name]
    stops = [station for station in route_stations if any(
        station == a or station == b for a, b in data.keys()
    )]

    if 開始駅 not in route_stations:
        await interaction.response.send_message(
            "開始駅は路線上の駅ではありません。",
            ephemeral=True
        )
        return

    if 終了駅 not in route_stations:
        await interaction.response.send_message(
            "終了駅は路線上の駅ではありません。",
            ephemeral=True
        )
        return

    if 開始駅 not in stops:
        await interaction.response.send_message(
            "開始駅は停車駅ではありません。",
            ephemeral=True
        )
        return

    if 終了駅 not in stops:
        await interaction.response.send_message(
            "終了駅は停車駅ではありません。",
            ephemeral=True
        )
        return

    start_idx = route_stations.index(開始駅)
    end_idx = route_stations.index(終了駅)

    if start_idx <= end_idx:
        full_path = route_stations[start_idx:end_idx + 1]
    else:
        full_path = list(reversed(route_stations[end_idx:start_idx + 1]))

    path = [station for station in full_path if station in stops]

    if not path or path[0] != 開始駅 or path[-1] != 終了駅:
        await interaction.response.send_message(
            "その種別はこの区間を走行しません",
            ephemeral=True
        )
        return

    try:
        current = datetime.strptime(開始時間, "%H:%M").replace(second=0, microsecond=0)
    except ValueError:
        await interaction.response.send_message(
            "開始時間の形式は HH:MM です。",
            ephemeral=True
        )
        return

    lines = [f"【{train_type}】"]
    lines.append(f"{path[0]} {current.strftime('%H:%M:%S')}発")

    for index in range(1, len(path)):
        prev_station = path[index - 1]
        station = path[index]
        travel_time = data.get((prev_station, station)) or data.get((station, prev_station))

        if travel_time is None:
            await interaction.response.send_message(
                "その種別はこの区間を走行しません",
                ephemeral=True
            )
            return

        current += timedelta(seconds=travel_time)
        arrival = round_up_to_30_seconds(current)

        if station == path[-1]:
            lines.append(f"{station} {arrival.strftime('%H:%M:%S')}着")
            current = arrival
        else:
            departure = arrival + timedelta(seconds=30)
            lines.append(
                f"{station} {arrival.strftime('%H:%M:%S')}着 {departure.strftime('%H:%M:%S')}発"
            )
            current = departure

    await interaction.response.send_message("\n".join(lines))


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
        await interaction.response.send_modal(
            TrainInfoModal(
                self.route_name,
                self.composition_index + 1,
                self.total_compositions,
                self.all_trains_data,
                self.callback
            )
        )


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
        await interaction.response.send_modal(
            ManualTrainInfoModal(
                self.route_name,
                self.composition_index + 1,
                self.total_compositions,
                self.all_trains_data,
                self.callback
            )
        )


class TrainInfoModal(discord.ui.Modal):
    def __init__(self, route_name: str, composition_index: int, total_compositions: int, all_trains_data: list, callback=None):
        super().__init__(title=f"編成 {composition_index}/{total_compositions}")
        self.route_name = route_name
        self.composition_index = composition_index
        self.total_compositions = total_compositions
        self.all_trains_data = all_trains_data
        self.callback = callback

    train_type = discord.ui.TextInput(
        label="種別",
        placeholder="普通/快速/急行/準急/区間急行/快速急行",
        required=True
    )
    departure_time = discord.ui.TextInput(
        label="始発時刻",
        placeholder="HH:MM",
        required=True
    )
    start_station = discord.ui.TextInput(
        label="開始駅",
        required=True
    )
    end_station = discord.ui.TextInput(
        label="終了駅",
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        train_data = {
            "type": str(self.train_type),
            "departure": str(self.departure_time),
            "start": str(self.start_station),
            "end": str(self.end_station)
        }
        self.all_trains_data.append(train_data)

        if self.composition_index < self.total_compositions:
            view = NextCompositionView(
                self.route_name,
                self.composition_index,
                self.total_compositions,
                self.all_trains_data,
                self.callback
            )
            await interaction.response.send_message(
                f"編成 {self.composition_index} を記録しました\n次へボタンで編成 {self.composition_index + 1} を入力してください",
                view=view,
                ephemeral=True
            )
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

    train_type = discord.ui.TextInput(
        label="種別",
        placeholder="普通/快速/急行/準急/区間急行/快速急行",
        required=True
    )
    departure_time = discord.ui.TextInput(
        label="始発時刻",
        placeholder="HH:MM",
        required=True
    )
    start_station = discord.ui.TextInput(
        label="開始駅",
        required=True
    )
    end_station = discord.ui.TextInput(
        label="終了駅",
        required=True
    )
    avoid_station = discord.ui.TextInput(
        label="待避駅（任意）",
        required=False
    )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        train_data = {
            "type": str(self.train_type),
            "departure": str(self.departure_time),
            "start": str(self.start_station),
            "end": str(self.end_station),
            "avoid": str(self.avoid_station) if str(self.avoid_station).strip() else None
        }
        self.all_trains_data.append(train_data)

        if self.composition_index < self.total_compositions:
            view = ManualNextCompositionView(
                self.route_name,
                self.composition_index,
                self.total_compositions,
                self.all_trains_data,
                self.callback
            )
            await interaction.response.send_message(
                f"編成 {self.composition_index} を記録しました\n次へボタンで編成 {self.composition_index + 1} を入力してください",
                view=view,
                ephemeral=True
            )
        else:
            await interaction.response.defer()
            if self.callback:
                await self.callback(interaction, self.route_name, self.all_trains_data)
            else:
                await interaction.followup.send(f"全 {self.composition_index} 編成を記録しました", ephemeral=True)


@app_commands.choices(
    路線名=[
        app_commands.Choice(name="尾羽急本線", value="尾羽急本線"),
        app_commands.Choice(name="空港線", value="空港線")
    ],
    編成数=[
        app_commands.Choice(name="1編成", value=1),
        app_commands.Choice(name="2編成", value=2),
        app_commands.Choice(name="3編成", value=3),
        app_commands.Choice(name="4編成", value=4),
        app_commands.Choice(name="5編成", value=5)
    ]
)
@bot.tree.command(name="create-emp", description="最大5編成列車作成（フォーム入力）")
async def create_emp(
    interaction: discord.Interaction,
    路線名: app_commands.Choice[str],
    編成数: int
):
    if not await check_role(interaction):
        return

    route_name = 路線名.value

    if route_name not in ROUTE_STATIONS:
        await interaction.response.send_message(
            f"{route_name} は未実装の路線です",
            ephemeral=True
        )
        return

    async def generate_emp_timetable(interaction: discord.Interaction, route_name: str, all_trains_data: list):
        messages = []

        for idx, train_data in enumerate(all_trains_data, 1):
            train_type = train_data["type"]
            departure = train_data["departure"]
            start_station = train_data["start"]
            end_station = train_data["end"]

            if train_type not in ROUTE_TRAIN_TYPES[route_name]:
                messages.append(f"❌ 編成{idx}: {train_type} は {route_name} では使用できません")
                continue

            timetable, error = calculate_times(route_name, train_type, start_station, end_station, departure)

            if error:
                messages.append(f"❌ 編成{idx}: {error}")
            else:
                messages.append(f"✅ 編成{idx}:")
                messages.extend(timetable)
                messages.append("")

        await interaction.followup.send("\n".join(messages), ephemeral=True)

    all_trains_data = []
    modal = TrainInfoModal(route_name, 1, 編成数, all_trains_data, generate_emp_timetable)
    await interaction.response.send_modal(modal)


@app_commands.choices(
    路線名=[
        app_commands.Choice(name="尾羽急本線", value="尾羽急本線"),
        app_commands.Choice(name="空港線", value="空港線")
    ],
    編成数=[
        app_commands.Choice(name="1編成", value=1),
        app_commands.Choice(name="2編成", value=2),
        app_commands.Choice(name="3編成", value=3),
        app_commands.Choice(name="4編成", value=4),
        app_commands.Choice(name="5編成", value=5),
        app_commands.Choice(name="6編成", value=6),
        app_commands.Choice(name="7編成", value=7),
        app_commands.Choice(name="8編成", value=8),
        app_commands.Choice(name="9編成", value=9),
        app_commands.Choice(name="10編成", value=10)
    ]
)
@bot.tree.command(name="create-man", description="最大10編成列車作成（詳細設定対応）")
async def create_man(
    interaction: discord.Interaction,
    路線名: app_commands.Choice[str],
    編成数: int
):
    if not await check_role(interaction):
        return

    route_name = 路線名.value

    if route_name not in ROUTE_STATIONS:
        await interaction.response.send_message(
            f"{route_name} は未実装の路線です",
            ephemeral=True
        )
        return

    async def generate_man_timetable(interaction: discord.Interaction, route_name: str, all_trains_data: list):
        messages = []

        for idx, train_data in enumerate(all_trains_data, 1):
            train_type = train_data["type"]
            departure = train_data["departure"]
            start_station = train_data["start"]
            end_station = train_data["end"]
            avoid_station = train_data.get("avoid")

            if train_type not in ROUTE_TRAIN_TYPES[route_name]:
                messages.append(f"❌ 編成{idx}: {train_type} は {route_name} では使用できません")
                continue

            timetable, error = calculate_times(route_name, train_type, start_station, end_station, departure)

            if error:
                messages.append(f"❌ 編成{idx}: {error}")
            else:
                messages.append(f"✅ 編成{idx}:")
                if avoid_station:
                    messages.append(f"（待避駅: {avoid_station}）")
                messages.extend(timetable)
                messages.append("")

        await interaction.followup.send("\n".join(messages), ephemeral=True)

    all_trains_data = []
    modal = ManualTrainInfoModal(route_name, 1, 編成数, all_trains_data, generate_man_timetable)
    await interaction.response.send_modal(modal)

# ==========================================
# create-auto（終日運用版）
# ==========================================

TURNBACK_TIME = 5  # 折返し時間（分）

@app_commands.choices(
    路線名=[
        app_commands.Choice(name="尾羽急本線", value="尾羽急本線"),
        app_commands.Choice(name="空港線", value="空港線")
    ]
)
@bot.tree.command(
    name="create-auto",
    description="終日自動ダイヤ作成"
)
async def create_auto(
    interaction: discord.Interaction,
    路線名: app_commands.Choice[str],
    開始駅: str,
    終了駅: str,
    開始時刻: str,
    終了時刻: str,
    編成数: int
):

    if not await check_role(interaction):
        return

    route_name = 路線名.value

    try:

        service_start = datetime.strptime(
            開始時刻,
            "%H:%M"
        )

        service_end = datetime.strptime(
            終了時刻,
            "%H:%M"
        )

    except ValueError:

        await interaction.response.send_message(
            "時刻は HH:MM 形式です",
            ephemeral=True
        )

        return

    if service_end <= service_start:
        service_end += timedelta(days=1)

    lines = []

    lines.append("【終日自動ダイヤ】")
    lines.append(route_name)
    lines.append(f"{開始駅} ⇔ {終了駅}")
    lines.append("")

    base_interval = 10

    for formation in range(編成数):

        depart = service_start + timedelta(
            minutes=formation * base_interval
        )

        lines.append(f"＝＝＝＝ 編成{formation+1} ＝＝＝＝")

        direction = 0

        while depart < service_end:

            if direction == 0:

                start = 開始駅
                end = 終了駅

            else:

                start = 終了駅
                end = 開始駅

            train_type = random.choice(
                get_available_train_types(route_name)
            )

            timetable, error = calculate_times(
                route_name,
                train_type,
                start,
                end,
                depart.strftime("%H:%M")
            )

            if error:
                break

            lines.append(
                f"{train_type}　{start}→{end}"
            )

            for row in timetable:
                lines.append("  " + row)

            last = timetable[-1]

            arrive_text = last.split()[-1]

            arrive = datetime.strptime(
                arrive_text,
                "%H:%M:%S"
            )

            arrive = depart.replace(
                hour=arrive.hour,
                minute=arrive.minute,
                second=arrive.second
            )

            if arrive < depart:
                arrive += timedelta(days=1)

            depart = arrive + timedelta(
                minutes=TURNBACK_TIME
            )

            direction = 1 - direction

            lines.append("")

    text = "\n".join(lines)

    if len(text) <= 1900:

        await interaction.response.send_message(
            text,
            ephemeral=True
        )

    else:

        chunks = []
        current = ""

        for line in lines:

            if len(current) + len(line) + 1 > 1900:

                chunks.append(current)
                current = ""

            current += line + "\n"

        if current:
            chunks.append(current)

        await interaction.response.send_message(
            chunks[0],
            ephemeral=True
        )

        for chunk in chunks[1:]:

            await interaction.followup.send(
                chunk,
                ephemeral=True
            )

# ==========================================
# 編成運用クラス
# ==========================================

TURNBACK_MINUTES = 5

class TrainFormation:

    def __init__(
        self,
        number: int,
        route_name: str,
        start_station: str,
        end_station: str,
        departure: datetime
    ):

        self.number = number
        self.route = route_name

        self.start_station = start_station
        self.end_station = end_station

        self.current_station = start_station

        self.next_departure = departure

        self.direction = 0

    def reverse(self):

        self.direction = 1 - self.direction

        self.current_station = (
            self.start_station
            if self.direction == 0
            else self.end_station
        )

    def get_start(self):

        if self.direction == 0:
            return self.start_station

        return self.end_station

    def get_end(self):

        if self.direction == 0:
            return self.end_station

        return self.start_station

# ==========================================
# 発車間隔・待避駅調整
# ==========================================

MIN_HEADWAY = 2          # 最低発車間隔（分）

used_departures = {}

def adjust_departure(
    station: str,
    depart: datetime
):

    while True:

        key = (
            station,
            depart.strftime("%H:%M")
        )

        if key not in used_departures:

            used_departures[key] = True
            return depart

        depart += timedelta(
            minutes=MIN_HEADWAY
        )


def choose_avoid_station(
    route_name,
    start_station,
    end_station
):

    path, _ = build_station_path(
        route_name,
        start_station,
        end_station
    )

    candidates = []

    for station in path[1:-1]:

        if station not in (
            start_station,
            end_station
        ):
            candidates.append(
                station
            )

    if not candidates:
        return None

    return random.choice(
        candidates
    )
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"{bot.user} でログインしました")


def start_web_server():
    port = int(os.environ.get("PORT", "5000"))
    print(f"Starting Flask on port {port}")

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False,
        use_reloader=False
    )


if __name__ == "__main__":
    print("Main started")

    # Flaskを別スレッドで起動
    web_thread = threading.Thread(
        target=start_web_server,
        daemon=True
    )
    web_thread.start()

    print("Web thread started")

    # Discord Botは1回だけ起動
    if TOKEN:
        bot.run(TOKEN)
    else:
        print("DISCORD_TOKEN が設定されていません")
