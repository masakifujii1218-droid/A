from datetime import datetime, timedelta
import json
import os
import random
import threading
import time

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

        def test_client(self):
            class _Client:
                def __init__(self, app):
                    self.app = app

                def get(self, path):
                    body = self.app.routes[path]()
                    return type(
                        "Response",
                        (),
                        {
                            "status_code": 200,
                            "get_data": lambda self, as_text=False: body if not as_text else body,
                        }
                    )()

            return _Client(self)

        def run(self, *args, **kwargs):
            return None

try:
    import discord
    from discord.ext import commands
    from discord import app_commands
except ModuleNotFoundError:
    class _DummyAppCommands:
        @staticmethod
        def choices(**_kwargs):
            def decorator(func):
                return func
            return decorator

        class Choice:
            def __init__(self, name=None, value=None):
                self.name = name
                self.value = value

            def __class_getitem__(cls, _item):
                return cls

    class _DummyIntents:
        members = False

        @staticmethod
        def default():
            return _DummyIntents()

    class _DummyDiscordUI:
        class View:
            def __init__(self, *args, **kwargs):
                pass

        class Modal:
            def __init__(self, *args, **kwargs):
                pass

        class Button:
            def __init__(self, *args, **kwargs):
                pass

        class TextInput:
            def __init__(self, *args, **kwargs):
                self.label = kwargs.get("label")

        def button(*args, **kwargs):
            def decorator(func):
                return func
            return decorator

    class _DummyDiscordModule:
        Intents = _DummyIntents
        Interaction = object
        ButtonStyle = type("ButtonStyle", (), {"primary": "primary"})
        ui = _DummyDiscordUI()

    discord = _DummyDiscordModule()
    app_commands = _DummyAppCommands()
    commands = None


import os

TOKEN = os.getenv("DISCORD_TOKEN")
app = Flask(__name__)


@app.route("/")
def health_check():
    return "Bot is running"

if commands is None:
    class _DummyBot:
        def __init__(self, *args, **kwargs):
            self.tree = self

        def command(self, *args, **kwargs):
            def decorator(func):
                return func
            return decorator

        def event(self, *args, **kwargs):
            def decorator(func):
                return func
            return decorator

        async def sync(self):
            return None

        def run(self, *args, **kwargs):
            return None

    bot = _DummyBot(command_prefix="/", intents=None)
else:
    intents = discord.Intents.default()
    intents.members = True
    bot = commands.Bot(
        command_prefix="/",
        intents=intents
    )
DATA_FILE = "trains.json"

# -------------------------
# JSON保存
# -------------------------

def load_trains():
    if not os.path.exists(DATA_FILE):
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump({}, f)

    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_trains(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# -------------------------
# ロールチェック
# -------------------------

COMMAND_ROLE_ID = 1510405214811852900

async def check_role(interaction: discord.Interaction) -> bool:
    """ロールをチェックして、権限がない場合はメッセージを送信"""
    if not any(role.id == COMMAND_ROLE_ID for role in interaction.user.roles):
        await interaction.response.send_message(
            "このコマンドを使う権限がありません。",
            ephemeral=True
        )
        return False
    return True

# -------------------------
# 駅順
# -------------------------

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

# -------------------------
# 普通
# -------------------------

LOCAL = {
    ("尾羽原","井口"):60,
    ("井口","梅郷"):60,
    ("梅郷","雲中"):30,
    ("雲中","安越"):60,
    ("安越","十川"):60,
    ("十川","千峰"):90,
    ("千峰","南雲谷"):80,
    ("南雲谷","雲谷"):120,
    ("雲谷","長峰"):75,
    ("長峰","西高徳"):90,
    ("西高徳","高徳"):90,
    ("高徳","明神前"):120,
    ("明神前","舞子台"):100,
    ("舞子台","紀田"):100,
    ("紀田","穂"):90,
    ("穂","瀬舞"):90,
    ("瀬舞","余美"):90,
    ("余美","千鳥"):90
}

# -------------------------
# 急行
# -------------------------

EXPRESS = {
    ("尾羽原","井口"):85,
    ("井口","安越"):85,
    ("安越","雲谷"):180,
    ("雲谷","高徳"):140,
    ("高徳","紀田"):180,
    ("紀田","千鳥"):120
}

# -------------------------
# 準急
# -------------------------

SEMI_EXPRESS = {
    ("尾羽原","井口"):90,
    ("井口","雲中"):120,
    ("雲中","安越"):60,
    ("安越","千峰"):120,
    ("千峰","雲谷"):150,
    ("雲谷","長峰"):120,
    ("長峰","高徳"):150,
    ("高徳","舞子台"):180,
    ("舞子台","紀田"):120,
    ("紀田","千鳥"):180
}

# -------------------------
# 快速
# -------------------------

RAPID = {
    ("尾羽原","井口"):60,
    ("井口","雲中"):90,
    ("雲中","安越"):60,
    ("安越","千峰"):120,
    ("千峰","雲谷"):180,
    ("雲谷","長峰"):75,
    ("長峰","西高徳"):90,
    ("西高徳","高徳"):90,
    ("高徳","明神前"):120,
    ("明神前","舞子台"):100,
    ("舞子台","紀田"):100,
    ("紀田","穂"):90,
    ("穂","瀬舞"):90,
    ("瀬舞","余美"):90,
    ("余美","千鳥"):90
}

# -------------------------
# 快速急行
# -------------------------

RAPID_EXPRESS = {
    ("尾羽原","高徳"):410,
    ("高徳","紀田"):180,
    ("紀田","千鳥"):120
}

# -------------------------
# 区間急行
# -------------------------

SECTION_EXPRESS = {
    ("尾羽原","井口"):90,
    ("井口","安越"):120,
    ("安越","雲谷"):210,
    ("雲谷","高徳"):180,
    ("高徳","明神前"):150,
    ("明神前","舞子台"):120,
    ("舞子台","紀田"):90,
    ("紀田","穂"):90,
    ("穂","瀬舞"):90,
    ("瀬舞","余美"):90,
    ("余美","千鳥"):90
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
            ("尾羽原","井口"):60,
            ("井口","梅郷"):60,
            ("梅郷","雲中"):30,
            ("雲中","安越"):60,
            ("安越","十川"):60,
            ("十川","千峰"):90,
            ("千峰","南雲谷"):80,
            ("南雲谷","雲谷"):120,
            ("雲谷","長峰"):75,
            ("長峰","西高徳"):90,
            ("西高徳","高徳"):90,
            ("高徳","新高徳"):120,
            ("新高徳","整備場"):120,
            ("整備場","空港"):120
        },
        "快速": {
            ("尾羽原","井口"):60,
            ("井口","雲中"):90,
            ("雲中","安越"):60,
            ("安越","千峰"):120,
            ("千峰","南雲谷"):180,
            ("南雲谷","雲谷"):180,
            ("雲谷","長峰"):75,
            ("長峰","西高徳"):90,
            ("西高徳","高徳"):90,
            ("高徳","新高徳"):120,
            ("新高徳","整備場"):120,
            ("整備場","空港"):120
        },
        "空港急行": {
            ("尾羽原","高徳"):410,
            ("高徳","新高徳"):90,
            ("新高徳","整備場"):90,
            ("整備場","空港"):90
        }
    }
}

# -------------------------
# 停車駅取得
# -------------------------

def get_stops(route_name, train_type):
    data = ROUTE_TRAIN_TYPES[route_name][train_type]

    stops = set()

    for a, b in data.keys():
        stops.add(a)
        stops.add(b)

    return list(stops)

# -------------------------
# 時刻計算
# -------------------------

def calculate_times(
    route_name,
    train_type,
    start_station,
    end_station,
    start_time
):
    data = ROUTE_TRAIN_TYPES[route_name][train_type]
    route_stations = ROUTE_STATIONS[route_name]

    if start_station not in route_stations:
        return None, "開始駅は路線上の駅ではありません"

    if end_station not in route_stations:
        return None, "終了駅は路線上の駅ではありません"

    stops = get_stops(route_name, train_type)

    if start_station not in stops:
        return None, "開始駅は停車駅ではありません"

    if end_station not in stops:
        return None, "終了駅は停車駅ではありません"

    edges = []

    for (a, b), sec in data.items():
        edges.append((a, b, sec))
        edges.append((b, a, sec))

    start_idx = route_stations.index(start_station)
    end_idx = route_stations.index(end_station)

    if start_idx < end_idx:
        path = route_stations[start_idx:end_idx + 1]
    else:
        path = list(
            reversed(
                route_stations[end_idx:start_idx + 1]
            )
        )

    current = datetime.strptime(
        start_time,
        "%H:%M"
    )

    timetable = [
        f"{path[0]} {current.strftime('%H:%M:%S')}"
    ]

    for i in range(len(path)-1):

        found = False

        for a, b, sec in edges:

            if a == path[i] and b == path[i+1]:

                current += timedelta(
                    seconds=sec
                )

                timetable.append(
                    f"{b} {current.strftime('%H:%M:%S')}"
                )

                found = True
                break

        if not found:
            return None, "その種別はこの区間を走行しません"

    return timetable, None


def build_station_path(route_name, start_station, end_station):
    if route_name not in ROUTE_STATIONS:
        return None, "未実装の路線です"

    route_stations = ROUTE_STATIONS[route_name]

    if start_station not in route_stations:
        return None, "開始駅は路線上の駅ではありません"

    if end_station not in route_stations:
        return None, "終了駅は路線上の駅ではありません"

    start_idx = route_stations.index(start_station)
    end_idx = route_stations.index(end_station)

    if start_idx <= end_idx:
        return route_stations[start_idx:end_idx + 1], None

    return list(reversed(route_stations[end_idx:start_idx + 1])), None


def get_available_train_types(route_name):
    return list(ROUTE_TRAIN_TYPES[route_name].keys())


def generate_auto_timetable(route_name, start_station, end_station, start_time, end_time, count):
    if count < 1:
        return None, "本数は1以上で指定してください"

    station_path, error = build_station_path(route_name, start_station, end_station)
    if error:
        return None, error

    if route_name not in ROUTE_TRAIN_TYPES:
        return None, f"{route_name} は未実装の路線です"

    try:
        start_dt = datetime.strptime(start_time, "%H:%M")
        end_dt = datetime.strptime(end_time, "%H:%M")
    except ValueError:
        return None, "時刻の形式は HH:MM です"

    start_minutes = start_dt.hour * 60 + start_dt.minute
    end_minutes = end_dt.hour * 60 + end_dt.minute

    if end_minutes < start_minutes:
        end_minutes += 24 * 60

    available_types = get_available_train_types(route_name)
    departures = []
    generated = []

    for _ in range(count):
        train_type = random.choice(available_types)
        departure_minutes = start_minutes + random.randint(0, max(0, end_minutes - start_minutes))

        while any(abs(departure_minutes - existing) < 2 for existing in departures):
            departure_minutes += 2
            if departure_minutes > end_minutes:
                departure_minutes = start_minutes

        departures.append(departure_minutes)
        departure_dt = datetime(2000, 1, 1) + timedelta(minutes=departure_minutes)
        departure_text = departure_dt.strftime("%H:%M")

        timetable, timetable_error = calculate_times(
            route_name,
            train_type,
            start_station,
            end_station,
            departure_text
        )
        if timetable_error:
            return None, timetable_error

        possible_avoid_stations = [
            station for station in station_path[1:-1]
            if station not in {start_station, end_station}
        ]
        avoid_station = None
        if possible_avoid_stations:
            avoid_station = random.choice(possible_avoid_stations)

        generated.append({
            "route": route_name,
            "type": train_type,
            "departure": departure_text,
            "departure_minutes": departure_minutes,
            "start": start_station,
            "end": end_station,
            "note": f"待避駅: {avoid_station}" if avoid_station else "待避駅: なし",
            "timetable": timetable,
        })

    generated.sort(key=lambda item: item["departure_minutes"])
    return generated, None

@app_commands.choices(
    路線名=[
        app_commands.Choice(name="尾羽急本線", value="尾羽急本線"),
        app_commands.Choice(name="空港線", value="空港線")
    ]
)
@bot.tree.command(name="create-auto", description="自動ダイヤ作成")
async def create_auto(
    interaction: discord.Interaction,
    路線名: app_commands.Choice[str],
    開始駅: str,
    終了駅: str,
    開始時刻: str,
    終了時刻: str,
    本数: int
):
    if not await check_role(interaction):
        return

    route_name = 路線名.value
    results, error = generate_auto_timetable(
        route_name,
        開始駅,
        終了駅,
        開始時刻,
        終了時刻,
        本数
    )

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


# -------------------------
# 複数編成フォーム（5編成まで）
# -------------------------

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
        """複数編成のダイヤを生成"""
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
        """複数編成のダイヤを生成（手動詳細設定対応）"""
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






    


@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"{bot.user} でログインしました")


def start_web_server():
    port = int(os.environ.get("PORT", "5000"))
    print(f"Starting Flask on port {port}")


if __name__ == "__main__":
    web_thread = threading.Thread(target=start_web_server, daemon=True)
    web_thread.start()

    if TOKEN:
        bot_thread = threading.Thread(target=bot.run, args=(TOKEN,), daemon=True)
        bot_thread.start()

    while True:
        time.sleep(60)