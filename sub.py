import discord
from discord.ext import commands, tasks
from discord import app_commands
import asyncio
import random
import io
import json
import re
from datetime import datetime

# ==========================================
# ⚙️ 定数・設定値
# ==========================================
ADMIN_ROLE_ID_POINTS = 1510405214811852900  # 管理者ロールIDに置き換えてください
WORK_ROLE_ID = 1510021467155202057          # お仕事コマンド実行可能ロールID
INBOX_CATEGORY_ID = 1513901626610553043     # Modmail受信カテゴリーID
LOG_CHANNEL_ID = 1513901627415855256        # チケットログ出力用チャンネルID
POINT_DATABASE_CHANNEL_ID = 1527164312634920980 # ポイントデータベースログチャンネルID

# 📈 株式データベースログ用チャンネルID（保存・復元の参照先）
STOCK_DATABASE_CHANNEL_ID = 1527164312634920980

# ==========================================
# 📦 グローバルデータストア
# ==========================================
# points_data: { "user_id_str": {"points": int, "logs": [str]} }
points_data = {}

# stocks_db: { "company_id": {"name": str, "buy_price": int, "sell_price": int, "stock": int, "is_active": bool, "history": [int, int, int]} }
stocks_db = {}

# user_stocks: { "user_id_str": { "company_id": int_amount } }
user_stocks = {}


# ==========================================
# 🛠️ 内部ヘルパー関数（ポイント＆株式）
# ==========================================
def get_user_data(user_id_str: str):
    if user_id_str not in points_data:
        points_data[user_id_str] = {"points": 0, "logs": []}
    return points_data[user_id_str]

def update_user_data(user_id_str: str, points: int, log_entry: str):
    data = get_user_data(user_id_str)
    data["points"] = points
    if "logs" not in data:
        data["logs"] = []
    data["logs"].append(log_entry)

def load_points():
    pass

async def sync_points_from_discord(bot: commands.Bot):
    pass

def setup_modmail_events(bot: commands.Bot):
    pass

# --- 株式ログ同期・バックアップ関数 ---
async def save_stocks_to_discord(bot: commands.Bot):
    """現在の stocks_db と user_stocks を Discord ログチャンネル(1527164312634920980)に JSON形式でバックアップ保存"""
    channel = bot.get_channel(STOCK_DATABASE_CHANNEL_ID)
    if not channel:
        try:
            channel = await bot.fetch_channel(STOCK_DATABASE_CHANNEL_ID)
        except Exception as e:
            print(f"❌ 株式バックアップチャンネル取得失敗: {e}")
            return

    backup_payload = {
        "type": "STOCK_DB_BACKUP",
        "timestamp": datetime.now().isoformat(),
        "stocks_db": stocks_db,
        "user_stocks": user_stocks
    }
    json_str = json.dumps(backup_payload, ensure_ascii=False, indent=2)
    
    # 2000文字超え対策（ファイル添付に切り替え）
    if len(json_str) > 1900:
        with io.StringIO(json_str) as f:
            file = discord.File(f, filename="stock_backup.json")
            await channel.send("📦 **[株式データ自動バックアップ]**", file=file)
    else:
        await channel.send(f"📦 **[株式データ自動バックアップ]**\n```json\n{json_str}\n```")

async def sync_stocks_from_discord(bot: commands.Bot):
    """Discordチャンネルの過去メッセージログを全スキャンし、最新バックアップから株式データを完全復元"""
    global stocks_db, user_stocks
    channel = bot.get_channel(STOCK_DATABASE_CHANNEL_ID)
    if not channel:
        try:
            channel = await bot.fetch_channel(STOCK_DATABASE_CHANNEL_ID)
        except Exception:
            print("⚠️ 株式データベースチャンネルにアクセスできませんでした。")
            return

    print("🔄 株式データをDiscordログからスキャン・復元中...")
    found_backup = False

    async for msg in channel.history(limit=200, oldest_first=False):
        # 1. 添付ファイル付きバックアップの読み込み
        if msg.attachments:
            for att in msg.attachments:
                if att.filename.endswith(".json"):
                    try:
                        content = await att.read()
                        data = json.loads(content.decode("utf-8"))
                        if isinstance(data, dict) and data.get("type") == "STOCK_DB_BACKUP":
                            stocks_db = data.get("stocks_db", {})
                            user_stocks = data.get("user_stocks", {})
                            found_backup = True
                            print("✅ ファイルバックアップから株式データを完全復元しました。")
                            break
                    except Exception as e:
                        print(f"❌ ファイルバックアップ解析エラー: {e}")
            if found_backup:
                break

        # 2. テキスト形式コードブロックバックアップの読み込み
        if msg.content and "STOCK_DB_BACKUP" in msg.content:
            try:
                match = re.search(r"```json\s*(\{.*?\})\s*```", msg.content, re.DOTALL)
                if match:
                    data = json.loads(match.group(1))
                    stocks_db = data.get("stocks_db", {})
                    user_stocks = data.get("user_stocks", {})
                    found_backup = True
                    print("✅ テキストバックアップから株式データを完全復元しました。")
                    break
            except Exception as e:
                print(f"❌ テキストバックアップ解析エラー: {e}")

    if not found_backup:
        print("ℹ️ 有効な株式バックアップが見つからなかったため、新規状態で開始します。")


# ==========================================
# 📈 株式価格の自動更新タスク (1時間周期)
# ==========================================
@tasks.loop(hours=1)
async def stock_price_update_task(bot: commands.Bot):
    if not stocks_db:
        return

    for cid, data in stocks_db.items():
        current_price = data["buy_price"]
        
        if "history" not in data:
            data["history"] = [current_price, current_price, current_price]
        
        data["history"].append(current_price)
        if len(data["history"]) > 3:
            data["history"].pop(0)

        rand_val = random.random()
        if rand_val < 0.01:
            rate = 2.00
        elif rand_val < 0.11:
            rate = random.uniform(0.30, 0.60)
        elif rand_val < 0.50:
            rate = random.uniform(0.01, 0.30)
        else:
            rate = random.uniform(-0.15, -0.01)

        new_buy_price = round(current_price * (1 + rate))
        if new_buy_price < 1:
            new_buy_price = 1

        new_sell_price = round(new_buy_price * 0.90)
        if new_sell_price < 1:
            new_sell_price = 1

        data["buy_price"] = new_buy_price
        data["sell_price"] = new_sell_price

    # 自動保存
    await save_stocks_to_discord(bot)


# ==========================================
# 🔘 UIコンポーネント (Modal & View)
# ==========================================

# --- Modmail 補助 View ---
class CloseRequestConfirmView(discord.ui.View):
    def __init__(self, channel_id, user_id, channel_name, staff_mention):
        super().__init__(timeout=None)
        self.channel_id = channel_id
        self.user_id = user_id
        self.channel_name = channel_name
        self.staff_mention = staff_mention

class StarRatingView(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=None)
        self.user_id = user_id

class SupportClaimView(discord.ui.View):
    def __init__(self, user_id, user_name):
        super().__init__(timeout=None)
        self.user_id = user_id
        self.user_name = user_name


# --- 管理者用 KABU パネル Modal & View ---
class CreateCompanyModal(discord.ui.Modal, title="新規会社の登録"):
    cid = discord.ui.TextInput(label="会社ID (半角英数)", placeholder="例: company_a", required=True)
    cname = discord.ui.TextInput(label="会社名", placeholder="例: AAA株式会社", required=True)
    buy_p = discord.ui.TextInput(label="初期購入価格(pt)", placeholder="1000", required=True)
    stock_cnt = discord.ui.TextInput(label="初期発行株式数", placeholder="100", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            b_price = int(self.buy_p.value)
            s_cnt = int(self.stock_cnt.value)
            s_price = round(b_price * 0.90)
        except ValueError:
            await interaction.response.send_message("❌ 価格と株式数は半角数字で入力してください。", ephemeral=True)
            return

        cid_str = self.cid.value.strip()
        stocks_db[cid_str] = {
            "name": self.cname.value.strip(),
            "buy_price": b_price,
            "sell_price": s_price,
            "stock": s_cnt,
            "is_active": True,
            "history": [b_price, b_price, b_price]
        }
        await save_stocks_to_discord(interaction.client)
        await interaction.response.send_message(f"✅ 会社 `{self.cname.value}` (ID: `{cid_str}`) を作成しました。", ephemeral=True)

class AdminKabuPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="➕ 新規会社作成", style=discord.ButtonStyle.success)
    async def create_company(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(CreateCompanyModal())


# --- ユーザー購入・売却 Modal & View ---
class BuyStockModal(discord.ui.Modal):
    def __init__(self, company_id: str):
        comp = stocks_db[company_id]
        super().__init__(title=f"株式購入 - {comp['name']}")
        self.company_id = company_id
        self.amount_input = discord.ui.TextInput(
            label=f"購入株数 (単価: {comp['buy_price']:,} pt / 在庫: {comp['stock']:,})",
            placeholder="購入数を入力",
            required=True
        )
        self.add_item(self.amount_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            amount = int(self.amount_input.value)
            if amount <= 0:
                raise ValueError()
        except ValueError:
            await interaction.response.send_message("❌ 1以上の有効な数値を入力してください。", ephemeral=True)
            return

        comp = stocks_db.get(self.company_id)
        if not comp or not comp["is_active"]:
            await interaction.response.send_message("❌ この株式は現在購入できません。", ephemeral=True)
            return

        if comp["stock"] < amount:
            await interaction.response.send_message(f"❌ 在庫が不足しています。(現在在庫: {comp['stock']:,} 株)", ephemeral=True)
            return

        total_cost = comp["buy_price"] * amount
        u_id = str(interaction.user.id)
        u_data = get_user_data(u_id)

        if u_data["points"] < total_cost:
            await interaction.response.send_message(f"❌ ポイントが不足しています。(必要: {total_cost:,} pt / 所持: {u_data['points']:,} pt)", ephemeral=True)
            return

        u_data["points"] -= total_cost
        comp["stock"] -= amount
        
        if u_id not in user_stocks:
            user_stocks[u_id] = {}
        user_stocks[u_id][self.company_id] = user_stocks[u_id].get(self.company_id, 0) + amount

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        u_data["logs"].append(f"[{now_str}] 📈 株式購入: {comp['name']} x{amount}株 (-{total_cost:,} pt)")

        await save_stocks_to_discord(interaction.client)

        embed = discord.Embed(title="✅ 株式購入完了", color=discord.Color.green())
        embed.add_field(name="購入銘柄", value=comp["name"])
        embed.add_field(name="購入数", value=f"{amount:,} 株")
        embed.add_field(name="支払ポイント", value=f"{total_cost:,} pt")
        embed.add_field(name="残高ポイント", value=f"{u_data['points']:,} pt", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

class UserBuySelectView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
        options = []
        for cid, data in stocks_db.items():
            if data["is_active"] and data["stock"] > 0:
                options.append(discord.SelectOption(
                    label=f"{data['name']} ({data['buy_price']:,} pt)",
                    value=cid,
                    description=f"在庫: {data['stock']:,} 株"
                ))

        if options:
            select = discord.ui.Select(placeholder="購入したい会社を選択...", options=options[:25])
            select.callback = self.select_callback
            self.add_item(select)

    async def select_callback(self, interaction: discord.Interaction):
        cid = interaction.data["values"][0]
        await interaction.response.send_modal(BuyStockModal(cid))

class SellStockModal(discord.ui.Modal):
    def __init__(self, company_id: str, max_amount: int):
        comp = stocks_db[company_id]
        super().__init__(title=f"株式売却 - {comp['name']}")
        self.company_id = company_id
        self.max_amount = max_amount
        self.amount_input = discord.ui.TextInput(
            label=f"売却株数 (買取単価: {comp['sell_price']:,} pt / 保有: {max_amount:,})",
            placeholder="売却数を入力",
            required=True
        )
        self.add_item(self.amount_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            amount = int(self.amount_input.value)
            if amount <= 0 or amount > self.max_amount:
                raise ValueError()
        except ValueError:
            await interaction.response.send_message(f"❌ 1 〜 {self.max_amount:,} の範囲で数値を入力してください。", ephemeral=True)
            return

        comp = stocks_db.get(self.company_id)
        u_id = str(interaction.user.id)
        u_data = get_user_data(u_id)

        total_return = comp["sell_price"] * amount
        u_data["points"] += total_return
        comp["stock"] += amount
        user_stocks[u_id][self.company_id] -= amount

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        u_data["logs"].append(f"[{now_str}] 💸 株式売却: {comp['name']} x{amount}株 (+{total_return:,} pt)")

        await save_stocks_to_discord(interaction.client)

        embed = discord.Embed(title="✅ 株式売却完了", color=discord.Color.gold())
        embed.add_field(name="売却銘柄", value=comp["name"])
        embed.add_field(name="売却数", value=f"{amount:,} 株")
        embed.add_field(name="受取ポイント", value=f"+{total_return:,} pt")
        embed.add_field(name="現在の残高", value=f"{u_data['points']:,} pt", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

class UserSellSelectView(discord.ui.View):
    def __init__(self, user_id_str: str):
        super().__init__(timeout=180)
        options = []
        owned = user_stocks.get(user_id_str, {})
        for cid, amount in owned.items():
            if amount > 0 and cid in stocks_db:
                comp = stocks_db[cid]
                options.append(discord.SelectOption(
                    label=f"{comp['name']} (保有: {amount:,} 株)",
                    value=cid,
                    description=f"買取単価: {comp['sell_price']:,} pt"
                ))

        if options:
            select = discord.ui.Select(placeholder="売却したい会社を選択...", options=options[:25])
            select.callback = self.select_callback
            self.add_item(select)

    async def select_callback(self, interaction: discord.Interaction):
        cid = interaction.data["values"][0]
        u_id = str(interaction.user.id)
        max_amount = user_stocks.get(u_id, {}).get(cid, 0)
        await interaction.response.send_modal(SellStockModal(cid, max_amount))


# ==========================================
# 🎰 スロット機能 Modals & Views
# ==========================================
class SlotBetModal(discord.ui.Modal, title="🎰 賭けポイントの設定"):
    bet_input = discord.ui.TextInput(
        label="賭けるポイント数を入力してください",
        placeholder="例: 100",
        min_length=1,
        max_length=10,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            bet_amount = int(self.bet_input.value)
            if bet_amount <= 0:
                await interaction.response.send_message("❌ 1ポイント以上を指定してください。", ephemeral=True)
                return
        except ValueError:
            await interaction.response.send_message("❌ 半角数字で有効な数値を入力してください。", ephemeral=True)
            return

        user_data = get_user_data(str(interaction.user.id))
        if user_data["points"] < bet_amount:
            await interaction.response.send_message(f"❌ ポイントが不足しています。（現在の所持: {user_data['points']:,} pt）", ephemeral=True)
            return

        view: SlotMainView = self.view
        view.user_bets[interaction.user.id] = bet_amount

        await interaction.response.send_message(
            f"✅ 賭けポイントを **{bet_amount:,} pt** に設定しました！\n「🎰 スロットスタート」ボタンを押してゲームを開始してください。",
            ephemeral=True
        )


class SlotMainView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.user_bets = {}
        self.jp_chance = {}

    @discord.ui.button(label="🪙 賭けるポイントを設定", style=discord.ButtonStyle.primary, custom_id="slot_set_bet")
    async def set_bet_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = SlotBetModal()
        modal.view = self
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="🎰 スロットスタート", style=discord.ButtonStyle.success, custom_id="slot_start")
    async def start_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = interaction.user.id
        bet_amount = self.user_bets.get(user_id, 0)

        if bet_amount <= 0:
            await interaction.response.send_message("❌ 先に「🪙 賭けるポイントを設定」ボタンから賭けポイントを設定してください。", ephemeral=True)
            return

        user_id_str = str(user_id)
        user_data = get_user_data(user_id_str)

        if user_data["points"] < bet_amount:
            await interaction.response.send_message(f"❌ ポイントが不足しています。（現在の所持: {user_data['points']:,} pt）", ephemeral=True)
            return

        await interaction.response.defer()

        symbols = ["🇯🇵", "🇺🇸", "💎", "🔔", "🚃"]
        reel = [random.choice(symbols) for _ in range(3)]
        reel_str = f"|  {reel[0]}  |  {reel[1]}  |  {reel[2]}  |"

        symbol_counts = {s: reel.count(s) for s in set(reel)}
        max_count = max(symbol_counts.values())

        payout_multiplier = 0
        result_title = ""
        result_color = discord.Color.red()
        jp_message = ""

        is_in_jp_chance = self.jp_chance.get(user_id, False)

        if max_count == 3:
            if is_in_jp_chance:
                payout_multiplier = 20
                result_title = "🎉💎 JACKPOT (2回連続3つ揃い)!! 💎🎉"
                result_color = discord.Color.gold()
                jp_message = "🔥 **超大暴走！2回連続3つ揃いでジャックポット獲得！！**"
                self.jp_chance[user_id] = False
            else:
                payout_multiplier = 5
                result_title = "🎊 3つ揃い！ 大勝利！ 🎊"
                result_color = discord.Color.green()
                jp_message = "⚡ **JACKPOT CHANCE発動！** 次回も3つ揃いが出れば **20倍**！！"
                self.jp_chance[user_id] = True
        elif max_count == 2:
            payout_multiplier = 2
            result_title = "✨ 2つ揃い！ WIN! ✨"
            result_color = discord.Color.blue()
            if is_in_jp_chance:
                jp_message = "※ジャックポットチャンスは失敗しました。"
            self.jp_chance[user_id] = False
        else:
            payout_multiplier = 0
            result_title = "💀 残念... 没収！ 💀"
            result_color = discord.Color.dark_gray()
            if is_in_jp_chance:
                jp_message = "※ジャックポットチャンスは失敗しました。"
            self.jp_chance[user_id] = False

        payout_points = bet_amount * payout_multiplier
        net_change = payout_points - bet_amount
        new_points = user_data["points"] + net_change

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        if net_change > 0:
            log_entry = f"[{now_str}] 🎰 スロット勝利 (+{net_change:,} pt / {reel[0]}{reel[1]}{reel[2]})"
        elif net_change < 0:
            log_entry = f"[{now_str}] 🎰 スロット敗北 ({net_change:,} pt / {reel[0]}{reel[1]}{reel[2]})"
        else:
            log_entry = f"[{now_str}] 🎰 スロット引き分け (±0 pt / {reel[0]}{reel[1]}{reel[2]})"

        update_user_data(user_id_str, new_points, log_entry)

        desc = f"### 🎰 【 {reel_str} 】 🎰\n\n"
        if jp_message:
            desc += f"{jp_message}\n\n"

        res_embed = discord.Embed(
            title=result_title,
            description=desc,
            color=result_color,
            timestamp=datetime.now()
        )
        res_embed.add_field(name="賭けポイント", value=f"`{bet_amount:,} pt`", inline=True)
        res_embed.add_field(name="獲得ポイント", value=f"`{payout_points:,} pt` (倍率: {payout_multiplier}倍)", inline=True)
        res_embed.add_field(name="現在の総保有", value=f"`{new_points:,} pt`", inline=False)

        await interaction.followup.send(content=interaction.user.mention, embed=res_embed)


# ==========================================
# 🚀 設定＆スラッシュコマンド定義
# ==========================================
def setup_slash_commands(bot: commands.Bot):
    load_points()

    # ------------------------------------------
    # 👑 1. 管理者専用 プレフィックスコマンド (!)
    # ------------------------------------------
    @bot.command(name="kabu")
    async def admin_kabu(ctx: commands.Context):
        if not any(role.id == ADMIN_ROLE_ID_POINTS for role in ctx.author.roles):
            await ctx.send("❌ このコマンドを実行する権限（管理者ロール）がありません。")
            return

        embed = discord.Embed(
            title="⚙️ 株式市場 管理専用パネル",
            description="会社の新規作成、株価の手動変更、販売の開始/停止、削除ができます。",
            color=discord.Color.dark_theme()
        )

        lines = []
        for cid, data in stocks_db.items():
            status = "🟢 販売中" if data["is_active"] else "🔴 販売停止"
            lines.append(f"• **{data['name']}** (ID: `{cid}`): 購入 `{data['buy_price']:,}pt` / 売却 `{data['sell_price']:,}pt` [{status}]")
        
        embed.add_field(name="📋 登録中の会社一覧", value="\n".join(lines) or "登録された会社はありません", inline=False)
        await ctx.send(embed=embed, view=AdminKabuPanelView())

    @bot.command(name="savekabu")
    async def force_save_kabu(ctx: commands.Context):
        """【管理者専用】現在の株式データを手動でログチャンネルへ保存"""
        if not any(role.id == ADMIN_ROLE_ID_POINTS for role in ctx.author.roles):
            await ctx.send("❌ 権限がありません。")
            return

        await save_stocks_to_discord(bot)
        await ctx.send("✅ 株式データをログチャンネルへ即時保存しました！")

    @bot.command(name="sendmessage")
    async def send_message_cmd(ctx: commands.Context, channel_id: int, *, content: str):
        if not any(role.id == ADMIN_ROLE_ID_POINTS for role in ctx.author.roles):
            await ctx.send("❌ このコマンドを実行する権限（管理者ロール）がありません。")
            return

        target_channel = bot.get_channel(channel_id)
        if not target_channel:
            try:
                target_channel = await bot.fetch_channel(channel_id)
            except Exception:
                await ctx.send("❌ 指定されたチャンネルが見つからないか、Botにアクセス権限がありません。")
                return

        try:
            await target_channel.send(content)
            await ctx.send(f"✅ <#{channel_id}> にメッセージを送信しました。")
        except Exception as e:
            await ctx.send(f"❌ メッセージの送信に失敗しました: {e}")

    # ------------------------------------------
    # 📨 2. Modmail系 スラッシュコマンド
    # ------------------------------------------
    @bot.tree.command(name="closereq", description="ユーザーにクローズ確認リクエストを送信します")
    async def close_request(interaction: discord.Interaction):
        channel = interaction.channel
        if not channel.category or channel.category_id != INBOX_CATEGORY_ID:
            await interaction.response.send_message("❌ このチャンネルでは実行できません。", ephemeral=True)
            return
        if not channel.topic or "User ID:" not in channel.topic:
            await interaction.response.send_message("❌ トピックからユーザーIDが読み取れません。", ephemeral=True)
            return

        await interaction.response.defer()

        try:
            parts = channel.topic.split("|")
            u_id = int(parts[0].replace("User ID:", "").strip())
            user = await bot.fetch_user(u_id)
        except:
            await interaction.followup.send("❌ ユーザー情報を取得できませんでした。")
            return

        req_embed = discord.Embed(
            title="🔒 問い合わせ終了の確認",
            description=f"スタッフ（{interaction.user.mention}）より、この問い合わせを終了（クローズ）して良いかの確認が届きました。\n\n問題が解決し、チケットを閉じてよろしければ、下の**「閉じる」**ボタンを押してください。",
            color=discord.Color.yellow()
        )
        view = CloseRequestConfirmView(
            channel_id=channel.id, user_id=user.id, channel_name=channel.name, staff_mention=interaction.user.mention
        )
        try:
            await user.send(embed=req_embed, view=view)
            await interaction.followup.send(f"📬 {user.mention} のDMへクローズ確認リクエストを送信しました。")
        except discord.Forbidden:
            await interaction.followup.send("❌ ユーザーのDMが閉じられているため、リクエストを送信できませんでした。")

    @bot.tree.command(name="close", description="チケットを強制クローズします")
    async def close_ticket(interaction: discord.Interaction):
        channel = interaction.channel
        if not channel.category or channel.category_id != INBOX_CATEGORY_ID:
            await interaction.response.send_message("❌ このチャンネルでは実行できません。", ephemeral=True)
            return
        if not channel.topic or "User ID:" not in channel.topic:
            await interaction.response.send_message("❌ トピックからユーザーIDが読み取れません。", ephemeral=True)
            return

        await interaction.response.send_message("🔒 強制クローズ処理中...")

        try:
            parts = channel.topic.split("|")
            u_id = int(parts[0].replace("User ID:", "").strip())
            user = await bot.fetch_user(u_id)
        except: user = None

        log_lines = []
        async for msg in channel.history(limit=100, oldest_first=True):
            if msg.embeds:
                for emb in msg.embeds:
                    author_name = emb.author.name if emb.author else "システム"
                    log_lines.append(f"[{msg.created_at.strftime('%Y-%m-%d %H:%M')}] {author_name}: {emb.description}")
            elif msg.content:
                log_lines.append(f"[{msg.created_at.strftime('%Y-%m-%d %H:%M')}] {msg.author.name}: {msg.content}")

        full_log_text = "\n".join(log_lines)

        log_channel = interaction.client.get_channel(LOG_CHANNEL_ID)
        if log_channel:
            log_embed = discord.Embed(
                title=f"🔒 チケットクローズログ: {channel.name}",
                description=f"**対象ユーザー:** {user.mention if user else channel.name}\n**クローズ実行者:** {interaction.user.mention} (強制クローズ)",
                color=discord.Color.red(), timestamp=datetime.now()
            )
            if len(full_log_text) > 3000 or len(full_log_text) == 0:
                with io.StringIO(full_log_text) as f:
                    file = discord.File(f, filename=f"log-{channel.name}.txt")
                    await log_channel.send(embed=log_embed, file=file)
            else:
                log_embed.add_field(name="📜 やり取り内容", value=f"```\n{full_log_text}\n```", inline=False)
                await log_channel.send(embed=log_embed)

        if user:
            try:
                end_embed = discord.Embed(title="🔒 問い合わせクローズ", description="運営スタッフによりチケットが閉じられました。", color=discord.Color.red())
                await user.send(end_embed)

                rating_embed = discord.Embed(
                    title="📝 問い合わせ評価のお願い",
                    description="今回のサポート対応はいかがでしたでしょうか？\n下のボタンから **⭐0 〜 ⭐5** の評価をお選びください。",
                    color=discord.Color.gold()
                )
                rating_view = StarRatingView(user_id=user.id)
                await user.send(embed=rating_embed, view=rating_view)
            except: pass

        await asyncio.sleep(2)
        await channel.delete()

    @bot.tree.command(name="change_staff", description="チケットの担当スタッフをリセットして交代します")
    async def change_staff(interaction: discord.Interaction):
        channel = interaction.channel
        if not channel.category or channel.category_id != INBOX_CATEGORY_ID:
            await interaction.response.send_message("❌ このチャンネルでは実行できません。", ephemeral=True)
            return
        if not channel.topic or "User ID:" not in channel.topic:
            await interaction.response.send_message("❌ トピックからユーザーIDが読み取れません。", ephemeral=True)
            return

        try:
            parts = channel.topic.split("|")
            u_id = int(parts[0].replace("User ID:", "").strip())
            user = await interaction.client.fetch_user(u_id)
        except:
            await interaction.response.send_message("❌ ユーザー情報の解析に失敗しました。", ephemeral=True)
            return

        await channel.edit(name=f"{user.name.lower()}", topic=f"User ID: {user.id}")
        new_view = SupportClaimView(user_id=user.id, user_name=user.name)
        reset_embed = discord.Embed(description="🔄 担当者がリセットされました。下のボタンを押して担当を交代してください。", color=discord.Color.yellow())
        await interaction.response.send_message(embed=reset_embed, view=new_view)

    # ------------------------------------------
    # 🪙 3. ポイントシステム スラッシュコマンド
    # ------------------------------------------
    @bot.tree.command(name="work", description="毎日の仕事をこなしてポイントを獲得します")
    @app_commands.checks.cooldown(1, 28800, key=lambda i: i.user.id)
    async def work_command(interaction: discord.Interaction):
        if not any(role.id == WORK_ROLE_ID for role in interaction.user.roles):
            embed = discord.Embed(description="❌ このコマンドを実行する権限（指定ロール）がありません。", color=discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=False)
            return

        if random.random() < 0.70:
            earned = random.randint(200, 300)
        else:
            earned = random.choice([random.randint(50, 199), random.randint(301, 400)])

        user_id_str = str(interaction.user.id)
        user_data = get_user_data(user_id_str)
        new_points = user_data["points"] + earned
        
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        log_entry = f"[{now_str}] 🪙 +{earned} pt (お仕事報酬)"
        
        update_user_data(user_id_str, new_points, log_entry)

        embed = discord.Embed(
            title="💼 お仕事完了！",
            description=f"{interaction.user.mention}さんが仕事を完了しました。\n\n獲得: **{earned}** ポイント 🪙",
            color=discord.Color.green(),
            timestamp=datetime.now()
        )
        embed.add_field(name="現在の総保有", value=f"`{new_points} pt`")
        await interaction.response.send_message(embed=embed, ephemeral=False)

        log_channel = interaction.client.get_channel(POINT_DATABASE_CHANNEL_ID)
        if log_channel:
            noti_embed = discord.Embed(title="📥 ポイント変動通知 (お仕事)", color=discord.Color.green(), timestamp=datetime.now())
            noti_embed.add_field(name="対象者", value=interaction.user.mention, inline=True)
            noti_embed.add_field(name="対象者ID", value=f"`{interaction.user.id}`", inline=True)
            noti_embed.add_field(name="変動値", value=f"+{earned} pt", inline=True)
            noti_embed.add_field(name="理由", value="お仕事報酬", inline=False)
            await log_channel.send(embed=noti_embed)

    @work_command.error
    async def work_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CommandOnCooldown):
            total_seconds = int(error.retry_after)
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            time_str = f"**{hours}時間** " if hours > 0 else ""
            time_str += f"**{minutes}分**"
            
            embed = discord.Embed(
                title="⏳ まだお仕事はできません",
                description=f"お仕事のやりすぎです！次のお仕事まであと {time_str} お待ちください。",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

    @bot.tree.command(name="points", description="指定したユーザー（または自分）の保有ポイントを確認します")
    @app_commands.describe(user="ポイントを確認したいユーザーを指定（未指定で自分）")
    async def points_command(interaction: discord.Interaction, user: discord.User = None):
        target_user = user or interaction.user
        user_data = get_user_data(str(target_user.id))

        embed = discord.Embed(
            title="🪙 ポイント確認",
            description=f"{target_user.mention} さんの現在の残高です。",
            color=discord.Color.gold(),
            timestamp=datetime.now()
        )
        embed.add_field(name="ポイント残高", value=f"**{user_data['points']}** pt", inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=False)

    @bot.tree.command(name="pointlog", description="ポイントの利用履歴（通帳）を最大100件確認します")
    @app_commands.describe(user="履歴を確認したいユーザーを指定（未指定で自分）")
    async def pointlog_command(interaction: discord.Interaction, user: discord.User = None):
        target_user = user or interaction.user
        user_data = get_user_data(str(target_user.id))

        embed = discord.Embed(
            title="📜 ポイント利用明細（通帳）",
            description=f"{target_user.mention} さんの過去の履歴です。",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )

        logs = user_data.get("logs", [])
        if not logs:
            embed.description += "\n\n*履歴はまだありません。*"
            await interaction.response.send_message(embed=embed, ephemeral=False)
            return

        recent_logs = list(reversed(logs))[:100]
        full_log_text = "\n".join(recent_logs)

        if len(full_log_text) > 850:
            embed.description += "\n\n📋 履歴数が多いため、テキストファイルを作成して添付しました。"
            with io.StringIO(full_log_text) as f:
                file = discord.File(f, filename=f"passbook-{target_user.name}.txt")
                await interaction.response.send_message(embed=embed, file=file, ephemeral=False)
        else:
            embed.add_field(name="直近の履歴（最大100件）", value=f"```\n{full_log_text}\n```", inline=False)
            await interaction.response.send_message(embed=embed, ephemeral=False)

    @bot.tree.command(name="rankings", description="ポイントの所持数ランキング上位10名を表示します")
    async def rankings_command(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)

        filtered_users = [
            (user_id, data) for user_id, data in points_data.items()
            if data.get("points", 0) >= 1
        ]

        if not filtered_users:
            embed = discord.Embed(
                title="🏆 ポイントランキング",
                description="現在、1ポイント以上を所持しているユーザーはいません。",
                color=discord.Color.gold()
            )
            await interaction.followup.send(embed=embed)
            return

        sorted_users = sorted(filtered_users, key=lambda item: item[1].get("points", 0), reverse=True)
        top_10 = sorted_users[:10]

        ranking_lines = []
        medals = ["🥇", "🥈", "🥉"]

        for index, (user_id_str, data) in enumerate(top_10, start=1):
            pts = data.get("points", 0)
            rank_display = medals[index - 1] if index <= 3 else f"**#{index}**"
            
            user_name = "不明なユーザー"
            try:
                user_id = int(user_id_str)
                user = interaction.client.get_user(user_id)
                if not user:
                    user = await interaction.client.fetch_user(user_id)
                if user:
                    user_name = discord.utils.escape_markdown(user.display_name)
            except Exception:
                user_name = f"ユーザー({user_id_str})"

            ranking_lines.append(f"{rank_display} **{user_name}**: `{pts:,} pt`")

        embed = discord.Embed(
            title="🏆 ポイント所持ランキング Top 10",
            description="\n".join(ranking_lines),
            color=discord.Color.gold(),
            timestamp=datetime.now()
        )
        embed.set_footer(text=f"対象ユーザー数: {len(filtered_users)}名")

        await interaction.followup.send(embed=embed)

    @bot.tree.command(name="give_points", description="【管理者専用】他人のポイントを増やします")
    @app_commands.describe(user="付与する対象のユーザー", amount="増やすポイント数", reason="付与する理由・説明")
    async def give_points_command(interaction: discord.Interaction, user: discord.User, amount: int, reason: str):
        if not any(role.id == ADMIN_ROLE_ID_POINTS for role in interaction.user.roles):
            embed = discord.Embed(description="❌ このコマンドを実行する権限がありません。", color=discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=False)
            return

        user_id_str = str(user.id)
        user_data = get_user_data(user_id_str)
        new_points = user_data["points"] + amount
        
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        log_entry = f"[{now_str}] 🪙 +{amount} pt (付与: {reason})"
        
        update_user_data(user_id_str, new_points, log_entry)

        res_embed = discord.Embed(
            title="✅ ポイント付与完了",
            description=f"{user.mention} に **{amount}** ポイントを付与しました。\n理由: {reason}",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=res_embed, ephemeral=False)

        log_channel = interaction.client.get_channel(POINT_DATABASE_CHANNEL_ID)
        if log_channel:
            noti_embed = discord.Embed(title="📥 ポイント変動通知 (付与)", color=discord.Color.green(), timestamp=datetime.now())
            noti_embed.add_field(name="対象者", value=user.mention, inline=True)
            noti_embed.add_field(name="対象者ID", value=f"`{user.id}`", inline=True)
            noti_embed.add_field(name="変動値", value=f"+{amount} pt", inline=True)
            noti_embed.add_field(name="理由", value=reason, inline=False)
            await log_channel.send(embed=noti_embed)

    @bot.tree.command(name="take_points", description="【管理者専用】他人のポイントを消費・減算します")
    @app_commands.describe(user="消費させる対象のユーザー", amount="減らすポイント数", reason="消費する理由・目的")
    async def take_points_command(interaction: discord.Interaction, user: discord.User, amount: int, reason: str):
        if not any(role.id == ADMIN_ROLE_ID_POINTS for role in interaction.user.roles):
            embed = discord.Embed(description="❌ このコマンドを実行する権限がありません。", color=discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=False)
            return

        user_id_str = str(user.id)
        user_data = get_user_data(user_id_str)
        new_points = user_data["points"] - amount
        
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        log_entry = f"[{now_str}] 💸 -{amount} pt (消費: {reason})"
        
        update_user_data(user_id_str, new_points, log_entry)

        res_embed = discord.Embed(
            title="⚠️ ポイント消費",
            description=f"{user.mention} のポイントを **{amount}** 消費しました。\n目的・理由: {reason}",
            color=discord.Color.orange()
        )
        await interaction.response.send_message(embed=res_embed, ephemeral=False)

        log_channel = interaction.client.get_channel(POINT_DATABASE_CHANNEL_ID)
        if log_channel:
            noti_embed = discord.Embed(title="📤 ポイント変動通知 (消費)", color=discord.Color.red(), timestamp=datetime.now())
            noti_embed.add_field(name="対象者", value=user.mention, inline=True)
            noti_embed.add_field(name="対象者ID", value=f"`{user.id}`", inline=True)
            noti_embed.add_field(name="変動値", value=f"-{amount} pt", inline=True)
            noti_embed.add_field(name="使用用途（理由）", value=reason, inline=False)
            await log_channel.send(embed=noti_embed)

    # ------------------------------------------
    # 📈 4. 株式システム スラッシュコマンド (/kabu)
    # ------------------------------------------
    kabu_group = app_commands.Group(name="kabu", description="株式取引・情報コマンド")

    @kabu_group.command(name="buy", description="販売中の株式を購入します")
    async def kabu_buy(interaction: discord.Interaction):
        view = UserBuySelectView()
        if not view.children:
            await interaction.response.send_message("❌ 現在購入できる会社はありません。", ephemeral=True)
            return
        await interaction.response.send_message("🏢 購入したい会社を選択してください:", view=view, ephemeral=True)

    @kabu_group.command(name="sell", description="保有している株式を売却します")
    async def kabu_sell(interaction: discord.Interaction):
        user_id_str = str(interaction.user.id)
        view = UserSellSelectView(user_id_str)
        if not view.children:
            await interaction.response.send_message("❌ 売却できる保有株がありません。", ephemeral=True)
            return
        await interaction.response.send_message("💸 売却したい会社を選択してください:", view=view, ephemeral=True)

    @kabu_group.command(name="company", description="現在株を販売・売り出し中の会社一覧を表示します")
    async def kabu_company(interaction: discord.Interaction):
        embed = discord.Embed(
            title="🏢 現在株を販売中の会社一覧",
            color=discord.Color.green(),
            timestamp=datetime.now()
        )

        active_lines = []
        for cid, data in stocks_db.items():
            if data["is_active"]:
                active_lines.append(
                    f"🟢 **{data['name']}** (ID: `{cid}`)\n"
                    f"├ 購入価格: **{data['buy_price']:,} pt** | 買取価格: **{data['sell_price']:,} pt**\n"
                    f"└ 残り在庫: **{data['stock']:,} 株**\n"
                )

        if active_lines:
            embed.description = "以下の会社で現在株の購入が可能です。\n`/kabu buy` で購入できます。\n\n" + "\n".join(active_lines)
        else:
            embed.description = "❌ 現在、株を販売している会社はありません。"

        await interaction.response.send_message(embed=embed, ephemeral=False)

    @kabu_group.command(name="info", description="登録されている全会社の状況と自分の保有株を表示します")
    async def kabu_info(interaction: discord.Interaction):
        embed = discord.Embed(title="📊 株式市場 & ポートフォリオ情報", color=discord.Color.blue(), timestamp=datetime.now())

        market_lines = []
        for cid, data in stocks_db.items():
            yesterday_p = data["history"][-1] if data.get("history") else data["buy_price"]
            diff = data["buy_price"] - yesterday_p
            pct = (diff / yesterday_p) * 100 if yesterday_p > 0 else 0
            diff_str = f"🔺+{diff:,}pt (+{pct:.1f}%)" if diff > 0 else (f"🔻{diff:,}pt ({pct:.1f}%)" if diff < 0 else "➖ 変化なし")
            
            history_list = data.get("history", [data["buy_price"]])
            history_str = " ➔ ".join([f"{p:,}pt" for p in history_list]) + f" ➔ **{data['buy_price']:,}pt**"
            status_str = "🟢 販売中" if data["is_active"] else "🔴 販売停止中"

            market_lines.append(
                f"🏢 **{data['name']}** [{status_str}]\n"
                f"├ 購入価格: **{data['buy_price']:,} pt** | 買取価格: **{data['sell_price']:,} pt** ({diff_str})\n"
                f"├ 残り在庫: {data['stock']:,} 株\n"
                f"└ 過去3日推移: `{history_str}`\n"
            )

        embed.add_field(name="🌐 登録全会社・市場状況", value="\n".join(market_lines) or "登録銘柄なし", inline=False)

        user_id_str = str(interaction.user.id)
        owned_dict = user_stocks.get(user_id_str, {})
        portfolio_lines = []
        total_eval = 0

        for cid, amount in owned_dict.items():
            if amount > 0 and cid in stocks_db:
                comp = stocks_db[cid]
                eval_val = amount * comp["sell_price"]
                total_eval += eval_val
                portfolio_lines.append(f"• **{comp['name']}**: {amount:,} 株 (売却想定額: `{eval_val:,} pt`)")

        portfolio_text = "\n".join(portfolio_lines) if portfolio_lines else "*保有している株はありません*"
        embed.add_field(name=f"💼 {interaction.user.display_name} さんの保有株式", value=f"{portfolio_text}\n\n**総売却可能評価額: `{total_eval:,} pt`**", inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=False)

    bot.tree.add_command(kabu_group)


# ==========================================
# 🏁 Bot起動エントリーポイント
# ==========================================
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# 設定のセットアップ実行
setup_slash_commands(bot)

@bot.event
async def on_ready():
    print(f"🤖 Botがログインしました: {bot.user} (ID: {bot.user.id})")
    
    # 1. バックアップログからデータを完全復元
    await sync_points_from_discord(bot)
    await sync_stocks_from_discord(bot)
    
    # 2. 定期タスクを安全に起動（★ここに追加★）
    if not stock_price_update_task.is_running():
        stock_price_update_task.start(bot)
        print("⏰ 株価自動更新タスクを起動しました。")
    
    # 3. スラッシュコマンドをDiscordへ同期
    try:
        synced = await bot.tree.sync()
        print(f"✅ スラッシュコマンドを {len(synced)} 件同期しました。")
    except Exception as e:
        print(f"❌ スラッシュコマンドの同期に失敗しました: {e}")

# TOKENをセットして実行（★一番最後に置く★）
# bot.run("YOUR_BOT_TOKEN")
