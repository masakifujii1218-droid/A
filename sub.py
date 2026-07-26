# ==========================================
# sub.py (Modmailシステム + ポイントシステム + 株式システム)
# ==========================================
import discord
from discord.ext import commands
from discord import app_commands
import asyncio
from datetime import datetime
import io
import os
import random
import json

# --- 固定設定 ---
INBOX_CATEGORY_ID = 1513901626610553043   # 問い合わせが入るカテゴリー
LOG_CHANNEL_ID = 1510042822533840936      # ログが送信されるチャンネル
RATING_CHANNEL_ID = 1510639675239432313   # ★評価と改善点が届くチャンネル
ADMIN_ROLE_ID = 1510405214811852900       # 運営・管理者ロールID

VERSION = "v8.0.0 (Kabu & Sendmessage Integrated)"

# --- ポイントシステム用設定 ---
POINT_DATABASE_CHANNEL_ID = 1527164312634920980  
WORK_ROLE_ID = 1510021467155202057           # /work を実行できるロールID
ADMIN_ROLE_ID_POINTS = 1510405214811852900    # 管理者ロールID

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
POINTS_FILE = os.path.join(BASE_DIR, "points.json")

points_data = {}

# ==========================================
# 📈 株式システム データ構造定義
# ==========================================
stocks_db = {
    "dia_corp": {
        "name": "ダイヤ鉱業",
        "buy_price": 100,
        "sell_price": 80,
        "stock": 1000,
        "is_active": True,
        "history": [80, 90, 100]
    }
}
user_stocks = {}  # { user_id_str: { company_id: amount } }

# ==========================================
# 💎 Discordチャンネルからポイントを自動復元・同期する関数
# ==========================================
async def sync_points_from_discord(bot: commands.Bot):
    global points_data
    print("【データベース】Discordのチャンネルからポイントデータの同期を開始します...")
    
    channel = bot.get_channel(POINT_DATABASE_CHANNEL_ID)
    if not channel:
        try:
            channel = await bot.fetch_channel(POINT_DATABASE_CHANNEL_ID)
        except Exception as e:
            print(f"【エラー】同期対象のチャンネルが見つかりません: {e}")
            return

    temp_data = {}
    count = 0

    async for message in channel.history(limit=5000, oldest_first=True):
        if message.author.id != bot.user.id or not message.embeds:
            continue
        
        embed = message.embeds[0]
        if embed.title and "ポイント変動通知" in embed.title:
            target_field = None
            change_field = None
            reason_field = "システムによる操作"

            for field in embed.fields:
                if field.name == "対象者ID":
                    target_field = field.value
                elif field.name == "変動値":
                    change_field = field.value
                elif field.name in ["理由", "使用用途（理由）"]:
                    reason_field = field.value

            if target_field and change_field:
                user_id_str = "".join(filter(str.isdigit, target_field))
                try:
                    change_amount = int(change_field.replace(" pt", "").replace("+", "").replace(" ", ""))
                except ValueError:
                    continue

                if user_id_str not in temp_data:
                    temp_data[user_id_str] = {"points": 0, "logs": []}

                temp_data[user_id_str]["points"] += change_amount
                
                time_str = message.created_at.strftime("%Y-%m-%d %H:%M")
                sign = "+" if change_amount >= 0 else ""
                emoji = "🪙" if change_amount >= 0 else "💸"
                log_entry = f"[{time_str}] {emoji} {sign}{change_amount} pt ({reason_field})"
                temp_data[user_id_str]["logs"].append(log_entry)
                
                count += 1

    points_data = temp_data
    save_points()
    print(f"【データベース】同期完了！計 {count} 件のログから {len(points_data)} 人分のデータを復元しました。")


# ==========================================
# ポイントデータ管理関数（ファイル保存）
# ==========================================
def load_points():
    global points_data
    if os.path.exists(POINTS_FILE):
        try:
            with open(POINTS_FILE, "r", encoding="utf-8") as f:
                points_data = json.load(f)
                print("【システム】ローカルのポイントデータを読み込みました。")
                return
        except Exception as e:
            print(f"データ読み込み失敗: {e}")
    points_data = {}

def save_points():
    try:
        with open(POINTS_FILE, "w", encoding="utf-8") as f:
            json.dump(points_data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"データ保存失敗: {e}")

def get_user_data(user_id: str):
    if user_id not in points_data:
        points_data[user_id] = {"points": 0, "logs": []}
        save_points()
    return points_data[user_id]

def update_user_data(user_id: str, points: int, log_entry: str):
    if user_id not in points_data:
        points_data[user_id] = {"points": 0, "logs": []}
    points_data[user_id]["points"] = points
    points_data[user_id]["logs"].append(log_entry)
    save_points()


# ==========================================
# 📊 [株システム] 管理者用 モーダル & View (!kabu)
# ==========================================
class AdminCreateCompanyModal(discord.ui.Modal):
    def __init__(self): super().__init__(title="🏢 新規会社の設立")
    c_id = discord.ui.TextInput(label="会社ID（識別用英数字）", placeholder="例: nintendo", required=True)
    c_name = discord.ui.TextInput(label="会社名", placeholder="例: 任天堂", required=True)
    c_buy_p = discord.ui.TextInput(label="販売価格(購入pt)", placeholder="例: 100", required=True)
    c_sell_p = discord.ui.TextInput(label="買取価格(売却pt)", placeholder="例: 80", required=True)
    c_stock = discord.ui.TextInput(label="初期発行株数", placeholder="例: 1000", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            cid = self.c_id.value.strip().lower()
            buy_p = int(self.c_buy_p.value)
            sell_p = int(self.c_sell_p.value)
            stock = int(self.c_stock.value)
            if buy_p <= 0 or sell_p <= 0 or stock <= 0: raise ValueError
        except ValueError:
            await interaction.response.send_message("❌ 正の整数を入力してください。", ephemeral=True)
            return

        stocks_db[cid] = {
            "name": self.c_name.value,
            "buy_price": buy_p,
            "sell_price": sell_p,
            "stock": stock,
            "is_active": True,
            "history": [buy_p, buy_p, buy_p]
        }
        await interaction.response.send_message(f"✅ 会社 **{self.c_name.value}**（ID: `{cid}`）を作成しました！", ephemeral=True)

class AdminUpdatePriceModal(discord.ui.Modal):
    def __init__(self): super().__init__(title="✏️ 株価（購入・売却価格）の手動変更")
    c_id = discord.ui.TextInput(label="対象の会社ID", placeholder="例: dia_corp", required=True)
    new_buy = discord.ui.TextInput(label="新しい【購入価格】(pt)", placeholder="例: 120", required=True)
    new_sell = discord.ui.TextInput(label="新しい【売却価格】(pt)", placeholder="例: 100", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        cid = self.c_id.value.strip().lower()
        if cid not in stocks_db:
            await interaction.response.send_message("❌ 指定された会社IDが存在しません。", ephemeral=True)
            return

        try:
            b_p = int(self.new_buy.value)
            s_p = int(self.new_sell.value)
            if b_p <= 0 or s_p <= 0: raise ValueError
        except ValueError:
            await interaction.response.send_message("❌ 正の整数を入力してください。", ephemeral=True)
            return

        comp = stocks_db[cid]
        comp["history"].pop(0)
        comp["history"].append(comp["buy_price"])
        comp["buy_price"] = b_p
        comp["sell_price"] = s_p

        await interaction.response.send_message(f"⚙️ **{comp['name']}** の価格を更新しました！\n• 購入価格: `{b_p:,} pt`\n• 売却価格: `{s_p:,} pt`", ephemeral=True)

class AdminToggleStatusModal(discord.ui.Modal):
    def __init__(self): super().__init__(title="🛑 販売開始 / 停止切り替え")
    c_id = discord.ui.TextInput(label="対象の会社ID", placeholder="例: dia_corp", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        cid = self.c_id.value.strip().lower()
        if cid not in stocks_db:
            await interaction.response.send_message("❌ 指定された会社IDが存在しません。", ephemeral=True)
            return

        comp = stocks_db[cid]
        comp["is_active"] = not comp["is_active"]
        status_str = "🟢 販売中" if comp["is_active"] else "🔴 販売停止中"
        await interaction.response.send_message(f"⚙️ **{comp['name']}** のステータスを **{status_str}** に切り替えました。", ephemeral=True)

class AdminDeleteCompanyModal(discord.ui.Modal):
    def __init__(self): super().__init__(title="🗑️ 会社の削除")
    c_id = discord.ui.TextInput(label="削除する会社ID", placeholder="例: dia_corp", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        cid = self.c_id.value.strip().lower()
        if cid not in stocks_db:
            await interaction.response.send_message("❌ 指定された会社IDが存在しません。", ephemeral=True)
            return

        comp_name = stocks_db[cid]["name"]
        del stocks_db[cid]
        await interaction.response.send_message(f"🗑️ 会社 **{comp_name}**（ID: `{cid}`）を完全削除しました。", ephemeral=True)

class AdminKabuPanelView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)

    @discord.ui.button(label="➕ 会社設立", style=discord.ButtonStyle.success)
    async def create_comp(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not any(role.id == ADMIN_ROLE_ID_POINTS for role in interaction.user.roles):
            await interaction.response.send_message("❌ 管理者権限がありません。", ephemeral=True)
            return
        await interaction.response.send_modal(AdminCreateCompanyModal())

    @discord.ui.button(label="✏️ 株価手動設定", style=discord.ButtonStyle.primary)
    async def update_price(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not any(role.id == ADMIN_ROLE_ID_POINTS for role in interaction.user.roles):
            await interaction.response.send_message("❌ 管理者権限がありません。", ephemeral=True)
            return
        await interaction.response.send_modal(AdminUpdatePriceModal())

    @discord.ui.button(label="🛑 販売開始/停止", style=discord.ButtonStyle.secondary)
    async def toggle_status(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not any(role.id == ADMIN_ROLE_ID_POINTS for role in interaction.user.roles):
            await interaction.response.send_message("❌ 管理者権限がありません。", ephemeral=True)
            return
        await interaction.response.send_modal(AdminToggleStatusModal())

    @discord.ui.button(label="🗑️ 会社削除", style=discord.ButtonStyle.danger)
    async def delete_comp(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not any(role.id == ADMIN_ROLE_ID_POINTS for role in interaction.user.roles):
            await interaction.response.send_message("❌ 管理者権限がありません。", ephemeral=True)
            return
        await interaction.response.send_modal(AdminDeleteCompanyModal())


# ==========================================
# 🛒 [株システム] メンバー用 モーダル & セレクトView (/kabu)
# ==========================================
class UserBuyModal(discord.ui.Modal):
    def __init__(self, company_id: str):
        comp = stocks_db[company_id]
        super().__init__(title=f"📈 {comp['name']} の株を購入")
        self.company_id = company_id

    amount_input = discord.ui.TextInput(label="購入株数", placeholder="例: 10", required=True, max_length=6)

    async def on_submit(self, interaction: discord.Interaction):
        comp = stocks_db.get(self.company_id)
        if not comp or not comp["is_active"]:
            await interaction.response.send_message("❌ この株は現在取引できません。", ephemeral=True)
            return

        try:
            amount = int(self.amount_input.value)
            if amount <= 0: raise ValueError
        except ValueError:
            await interaction.response.send_message("❌ 正の整数を入力してください。", ephemeral=True)
            return

        if amount > comp["stock"]:
            await interaction.response.send_message(f"❌ 在庫が足りません（残り: {comp['stock']:,} 株）", ephemeral=True)
            return

        total_cost = amount * comp["buy_price"]
        user_id_str = str(interaction.user.id)
        user_data = get_user_data(user_id_str)

        if user_data["points"] < total_cost:
            await interaction.response.send_message(f"❌ ポイントが足りません（必要: {total_cost:,} pt / 所持: {user_data['points']:,} pt）", ephemeral=True)
            return

        new_points = user_data["points"] - total_cost
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        update_user_data(user_id_str, new_points, f"[{now_str}] 💸 -{total_cost} pt ({comp['name']}株 {amount}株購入)")

        comp["stock"] -= amount
        if user_id_str not in user_stocks: user_stocks[user_id_str] = {}
        user_stocks[user_id_str][self.company_id] = user_stocks[user_id_str].get(self.company_id, 0) + amount

        embed = discord.Embed(
            title="🎉 株の購入完了！",
            description=f"**{comp['name']}** の株を **{amount:,} 株** 購入しました！\n支払額: **{total_cost:,} pt** (単価: {comp['buy_price']:,} pt)",
            color=discord.Color.green()
        )
        embed.add_field(name="残高ポイント", value=f"`{new_points:,} pt`")
        embed.add_field(name="現在の保有株数", value=f"`{user_stocks[user_id_str][self.company_id]:,} 株`")
        await interaction.response.send_message(embed=embed, ephemeral=True)

        log_channel = interaction.client.get_channel(POINT_DATABASE_CHANNEL_ID)
        if log_channel:
            noti_embed = discord.Embed(title="📥 ポイント変動通知 (株購入)", color=discord.Color.red(), timestamp=datetime.now())
            noti_embed.add_field(name="対象者", value=interaction.user.mention, inline=True)
            noti_embed.add_field(name="対象者ID", value=f"`{interaction.user.id}`", inline=True)
            noti_embed.add_field(name="変動値", value=f"-{total_cost} pt", inline=True)
            noti_embed.add_field(name="理由", value=f"{comp['name']}株購入 ({amount}株)", inline=False)
            await log_channel.send(embed=noti_embed)

class UserBuySelectView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)
        options = [
            discord.SelectOption(
                label=data["name"],
                value=cid,
                description=f"購入価格: {data['buy_price']:,}pt | 在庫: {data['stock']:,}株"
            ) for cid, data in stocks_db.items() if data["is_active"]
        ]
        if options:
            select = discord.ui.Select(placeholder="購入する会社を選択してください...", options=options)
            select.callback = self.callback
            self.add_item(select)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(UserBuyModal(self.children[0].values[0]))

class UserSellModal(discord.ui.Modal):
    def __init__(self, company_id: str):
        comp = stocks_db[company_id]
        super().__init__(title=f"💸 {comp['name']} の株を売却")
        self.company_id = company_id

    amount_input = discord.ui.TextInput(label="売却株数", placeholder="例: 5", required=True, max_length=6)

    async def on_submit(self, interaction: discord.Interaction):
        comp = stocks_db.get(self.company_id)
        user_id_str = str(interaction.user.id)
        owned = user_stocks.get(user_id_str, {}).get(self.company_id, 0)

        try:
            amount = int(self.amount_input.value)
            if amount <= 0: raise ValueError
        except ValueError:
            await interaction.response.send_message("❌ 正の整数を入力してください。", ephemeral=True)
            return

        if amount > owned:
            await interaction.response.send_message(f"❌ 保有株数が不足しています（所持: {owned:,} 株）", ephemeral=True)
            return

        total_return = amount * comp["sell_price"]
        user_data = get_user_data(user_id_str)

        user_stocks[user_id_str][self.company_id] -= amount
        comp["stock"] += amount

        new_points = user_data["points"] + total_return
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        update_user_data(user_id_str, new_points, f"[{now_str}] 🪙 +{total_return} pt ({comp['name']}株 {amount}株売却)")

        embed = discord.Embed(
            title="💰 株の売却完了！",
            description=f"**{comp['name']}** の株を **{amount:,} 株** 売却しました！\n受領額: **+{total_return:,} pt** (買取単価: {comp['sell_price']:,} pt)",
            color=discord.Color.gold()
        )
        embed.add_field(name="残高ポイント", value=f"`{new_points:,} pt`")
        embed.add_field(name="残りの保有株数", value=f"`{user_stocks[user_id_str][self.company_id]:,} 株`")
        await interaction.response.send_message(embed=embed, ephemeral=True)

        log_channel = interaction.client.get_channel(POINT_DATABASE_CHANNEL_ID)
        if log_channel:
            noti_embed = discord.Embed(title="📥 ポイント変動通知 (株売却)", color=discord.Color.green(), timestamp=datetime.now())
            noti_embed.add_field(name="対象者", value=interaction.user.mention, inline=True)
            noti_embed.add_field(name="対象者ID", value=f"`{interaction.user.id}`", inline=True)
            noti_embed.add_field(name="変動値", value=f"+{total_return} pt", inline=True)
            noti_embed.add_field(name="理由", value=f"{comp['name']}株売却 ({amount}株)", inline=False)
            await log_channel.send(embed=noti_embed)

class UserSellSelectView(discord.ui.View):
    def __init__(self, user_id_str: str):
        super().__init__(timeout=60)
        owned_dict = user_stocks.get(user_id_str, {})
        options = [
            discord.SelectOption(
                label=stocks_db[cid]["name"],
                value=cid,
                description=f"所持: {amount:,}株 | 買取価格: {stocks_db[cid]['sell_price']:,}pt"
            ) for cid, amount in owned_dict.items() if amount > 0 and cid in stocks_db
        ]
        if options:
            select = discord.ui.Select(placeholder="売却する株を選択してください...", options=options)
            select.callback = self.callback
            self.add_item(select)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(UserSellModal(self.children[0].values[0]))


# ==========================================
# [DM用] 改善点・問題点の入力モーダル
# ==========================================
class FeedbackModal(discord.ui.Modal):
    def __init__(self, rating_stars: int, user_id: int):
        super().__init__(title="問い合わせへのフィードバック")
        self.rating_stars = rating_stars
        self.user_id = user_id

    feedback_text = discord.ui.TextInput(
        label="改善点・問題点があればご記入ください",
        style=discord.TextStyle.paragraph,
        placeholder="ここに入力してください（任意）",
        required=False,
        max_length=1000
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        stars_str = "⭐" * self.rating_stars if self.rating_stars > 0 else "🖤 (星0)"
        embed = discord.Embed(
            title="📊 問い合わせ評価・フィードバック受信",
            color=discord.Color.purple(),
            timestamp=datetime.now()
        )
        embed.add_field(name="👤 評価ユーザー", value=f"<@{self.user_id}> (`{self.user_id}`)", inline=False)
        embed.add_field(name="⭐ 満足度評価", value=f"**{stars_str}** ({self.rating_stars}/5)", inline=False)
        embed.add_field(name="💬 改善点・問題点", value=self.feedback_text.value or "*記述なし*", inline=False)

        rating_channel = interaction.client.get_channel(RATING_CHANNEL_ID)
        if rating_channel:
            await rating_channel.send(embed=embed)
        await interaction.followup.send("ご協力ありがとうございました！", ephemeral=True)


# ==========================================
# [DM用] 星評価（0〜5）のボタン
# ==========================================
class StarRatingView(discord.ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=600)
        self.user_id = user_id

    async def handle_rating(self, interaction: discord.Interaction, stars: int):
        for child in self.children:
            child.disabled = True
        await interaction.message.edit(view=self)
        await interaction.response.send_modal(FeedbackModal(rating_stars=stars, user_id=self.user_id))

    @discord.ui.button(label="⭐0", style=discord.ButtonStyle.secondary, custom_id="star_0")
    async def star0(self, interaction: discord.Interaction, button: discord.ui.Button): await self.handle_rating(interaction, 0)
    @discord.ui.button(label="⭐1", style=discord.ButtonStyle.danger, custom_id="star_1")
    async def star1(self, interaction: discord.Interaction, button: discord.ui.Button): await self.handle_rating(interaction, 1)
    @discord.ui.button(label="⭐2", style=discord.ButtonStyle.danger, custom_id="star_2")
    async def star2(self, interaction: discord.Interaction, button: discord.ui.Button): await self.handle_rating(interaction, 2)
    @discord.ui.button(label="⭐3", style=discord.ButtonStyle.success, custom_id="star_3")
    async def star3(self, interaction: discord.Interaction, button: discord.ui.Button): await self.handle_rating(interaction, 3)
    @discord.ui.button(label="⭐4", style=discord.ButtonStyle.success, custom_id="star_4")
    async def star4(self, interaction: discord.Interaction, button: discord.ui.Button): await self.handle_rating(interaction, 4)
    @discord.ui.button(label="⭐5", style=discord.ButtonStyle.primary, custom_id="star_5")
    async def star5(self, interaction: discord.Interaction, button: discord.ui.Button): await self.handle_rating(interaction, 5)


# ==========================================
# [DM用] クローズ同意ボタン
# ==========================================
class CloseRequestConfirmView(discord.ui.View):
    def __init__(self, channel_id: int, user_id: int, channel_name: str, staff_mention: str):
        super().__init__(timeout=None)
        self.channel_id = channel_id
        self.user_id = user_id
        self.channel_name = channel_name
        self.staff_mention = staff_mention

    @discord.ui.button(label="🔒 閉じる", style=discord.ButtonStyle.danger, custom_id="user_confirm_close")
    async def confirm_close(self, interaction: discord.Interaction, button: discord.ui.Button):
        bot = interaction.client
        ticket_channel = bot.get_channel(self.channel_id)
        
        button.disabled = True
        button.label = "クローズされました"
        await interaction.message.edit(view=self)
        await interaction.response.defer()

        log_lines = []
        if ticket_channel:
            await ticket_channel.send("🔒 ユーザーがクローズを承諾しました。ログをエクスポート中...")
            async for msg in ticket_channel.history(limit=100, oldest_first=True):
                if msg.embeds:
                    for emb in msg.embeds:
                        author_name = emb.author.name if emb.author else "システム"
                        log_lines.append(f"[{msg.created_at.strftime('%Y-%m-%d %H:%M')}] {author_name}: {emb.description}")
                elif msg.content:
                    log_lines.append(f"[{msg.created_at.strftime('%Y-%m-%d %H:%M')}] {msg.author.name}: {msg.content}")

        full_log_text = "\n".join(log_lines)

        log_channel = bot.get_channel(LOG_CHANNEL_ID)
        if log_channel:
            log_embed = discord.Embed(
                title=f"🔒 チケットクローズログ: {self.channel_name}",
                description=f"**対象ユーザー:** <@{self.user_id}>\n**クローズ方式:** ユーザー同意によるクローズ (`/closereq`)",
                color=discord.Color.red(), timestamp=datetime.now()
            )
            if len(full_log_text) > 3000 or len(full_log_text) == 0:
                with io.StringIO(full_log_text) as f:
                    file = discord.File(f, filename=f"log-{self.channel_name}.txt")
                    await log_channel.send(embed=log_embed, file=file)
            else:
                log_embed.add_field(name="📜 やり取り内容", value=f"```\n{full_log_text}\n```", inline=False)
                await log_channel.send(embed=log_embed)

        if ticket_channel:
            await asyncio.sleep(2)
            await ticket_channel.delete()

        rating_embed = discord.Embed(
            title="📝 問い合わせ評価のお願い",
            description="今回のサポート対応はいかがでしたでしょうか？\n下のボタンから **⭐0 〜 ⭐5** の評価をお選びください。",
            color=discord.Color.gold()
        )
        rating_view = StarRatingView(user_id=self.user_id)
        await interaction.followup.send(embed=rating_embed, view=rating_view)


# ==========================================
# スタッフ用：担当者登録用ボタン
# ==========================================
class SupportClaimView(discord.ui.View):
    def __init__(self, user_id: int, user_name: str):
        super().__init__(timeout=None)
        self.user_id = user_id
        self.user_name = user_name

    @discord.ui.button(label="🙋‍♂️ 担当する", style=discord.ButtonStyle.primary, custom_id="claim_ticket")
    async def claim(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = interaction.channel
        if "-with-" in channel.name:
            await interaction.response.send_message("❌ このチケットは既に他のスタッフが担当しています。", ephemeral=True)
            return

        staff = interaction.user
        new_channel_name = f"{self.user_name.lower()}-with-{staff.name.lower()}"
        await channel.edit(name=new_channel_name, topic=f"User ID: {self.user_id} | Staff ID: {staff.id}")
        
        button.label = f"担当者: {staff.name}"
        button.style = discord.ButtonStyle.success
        button.disabled = True
        await interaction.message.edit(view=self)
        
        await interaction.response.send_message(f"🤝 {staff.mention} が担当者になりました。通常発言がユーザーに転送されます。")
        
        try:
            user = await interaction.client.fetch_user(self.user_id)
            if user:
                embed = discord.Embed(
                    description=f"💁‍♂️ あなたの問い合わせの担当者が **{staff.mention}** に決定しました。\n用件をそのままお話しください。",
                    color=discord.Color.green()
                )
                await user.send(embed=embed)
        except Exception as e:
            await channel.send(f"⚠️ ユーザーへのDM通知に失敗: {e}")


# ==========================================
# Modmail コアロジック (イベント処理)
# ==========================================
def setup_modmail_events(bot: commands.Bot):

    @bot.event
    async def on_message(message: discord.Message):
        if message.author.bot:
            return

        # 1. ユーザー ➡ BotへのDM
        if isinstance(message.channel, discord.DMChannel):
            if not bot.guilds: return
            guild = bot.guilds[0]
            category = guild.get_channel(INBOX_CATEGORY_ID)
            if not category: return

            existing_channel = None
            for ch in category.text_channels:
                if ch.topic and f"User ID: {message.author.id}" in ch.topic:
                    existing_channel = ch
                    break

            if not existing_channel:
                channel_name = f"{message.author.name.lower()}"
                
                staff_role = guild.get_role(ADMIN_ROLE_ID)
                overwrites = {
                    guild.default_role: discord.PermissionOverwrite(read_messages=False),
                    guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
                }
                if staff_role:
                    overwrites[staff_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_messages=True)

                existing_channel = await guild.create_text_channel(
                    name=channel_name, category=category, topic=f"User ID: {message.author.id}", overwrites=overwrites
                )

                dm_welcome = discord.Embed(
                    title="📩 問い合わせを受け付けました",
                    description="サーバー運営チームにメッセージが転送されました。\n担当者が決定するまでしばらくお待ちください。",
                    color=discord.Color.blue()
                )
                await message.channel.send(embed=dm_welcome)

                member = guild.get_member(message.author.id)
                roles_str = ", ".join([r.mention for r in member.roles if r != guild.default_role]) if member else "取得不可"
                join_at = member.joined_at.strftime('%Y/%m/%d %H:%M') if member and member.joined_at else "不明"

                info_embed = discord.Embed(title="📩 新規問い合わせチケット", color=discord.Color.orange())
                info_embed.add_field(name="👤 ユーザー名", value=f"{message.author.mention} ({message.author})", inline=True)
                info_embed.add_field(name="🆔 ユーザーID", value=f"`{message.author.id}`", inline=True)
                info_embed.add_field(name="📅 サーバー参加日", value=join_at, inline=False)
                info_embed.add_field(name="🛡️ 所持ロール", value=roles_str or "なし", inline=False)
                info_embed.add_field(name="💬 メッセージ", value=message.content, inline=False)

                view = SupportClaimView(user_id=message.author.id, user_name=message.author.name)
                await existing_channel.send(embed=info_embed, view=view)
                await message.add_reaction("✅")
                return

            user_embed = discord.Embed(description=message.content, color=discord.Color.green())
            user_embed.set_author(name=f"{message.author} (DM)", icon_url=message.author.display_avatar.url)
            await existing_channel.send(embed=user_embed)
            await message.add_reaction("✅")

        # 2. スタッフ側の発言 ➡ ユーザーのDMへ転送
        elif isinstance(message.channel, discord.TextChannel) and message.channel.category_id == INBOX_CATEGORY_ID:
            if message.content.startswith("/"): return
            if not message.channel.topic or "User ID:" not in message.channel.topic: return

            try:
                parts = message.channel.topic.split("|")
                u_id = int(parts[0].replace("User ID:", "").strip())
                user = await bot.fetch_user(u_id)
            except: return

            staff_embed = discord.Embed(description=message.content, color=discord.Color.blue())
            staff_embed.set_author(name="ダイヤ作成所", icon_url=message.guild.icon.url if message.guild.icon else None)
            
            try:
                await user.send(embed=staff_embed)
                await message.add_reaction("✈️")
            except discord.Forbidden:
                await message.channel.send("❌ ユーザーのDMが閉じられているため転送できませんでした。")

        # 他のプレフィックスコマンド（!kabu や !sendmessage など）を正しく実行させる処理
        await bot.process_commands(message)
import asyncio
import io
import random
from datetime import datetime
import discord
from discord import app_commands
from discord.ext import commands, tasks

# ==========================================
# 📈 株式価格の自動更新タスク (1時間周期)
# ==========================================
@tasks.loop(hours=1)
async def stock_price_update_task(bot: commands.Bot):
    """
    1時間ごとに株価を更新するバックグラウンドタスク
    - 1%  : 超大暴騰 (+200%)
    - 10% : 大高騰 (+30.0% 〜 +60.0%)
    - 39% : 通常上昇 (+1.0% 〜 +30.0%)
    - 50% : 下落 (-1.0% 〜 -15.0%)
    - 購入価格/売却価格は 1の位で四捨五入 (round)
    """
    if not stocks_db:
        return

    for cid, data in stocks_db.items():
        # アクティブ（販売中）でない銘柄も価格変動は計算（または active のみ限定も可能）
        current_price = data["buy_price"]
        
        # 過去3日の履歴更新 (最新の購入価格を履歴に追加し、直近3日分を維持)
        if "history" not in data:
            data["history"] = [current_price, current_price, current_price]
        
        # 履歴を1つ進める
        data["history"].append(current_price)
        if len(data["history"]) > 3:
            data["history"].pop(0)

        # 🎲 確率判定
        rand_val = random.random()  # 0.0 ~ 1.0

        if rand_val < 0.01:
            # 💣 超大暴騰 (1%) : +200%（3倍）
            rate = 2.00
        elif rand_val < 0.11:
            # 🚀 大高騰 (10%) : +30.0% 〜 +60.0%
            rate = random.uniform(0.30, 0.60)
        elif rand_val < 0.50:
            # 📈 通常上昇 (39%) : +1.0% 〜 +30.0%
            rate = random.uniform(0.01, 0.30)
        else:
            # 📉 下落 (50%) : -1.0% 〜 -15.0%
            rate = random.uniform(-0.15, -0.01)

        # 新しい購入価格の計算（1の位で四捨五入）
        new_buy_price = round(current_price * (1 + rate))
        
        # 最低価格は 1 pt に設定
        if new_buy_price < 1:
            new_buy_price = 1

        # 新しい売却価格（買取レート）：購入価格の 90%（1の位で四捨五入）
        new_sell_price = round(new_buy_price * 0.90)
        if new_sell_price < 1:
            new_sell_price = 1

        # データベース更新
        data["buy_price"] = new_buy_price
        data["sell_price"] = new_sell_price

    # 株式データの保存処理がある場合はここで呼び出し
    # save_stocks_db()


# ==========================================
# 管理・一般コマンド & 設定構築関数
# ==========================================
def setup_slash_commands(bot: commands.Bot):
    load_points()
    asyncio.create_task(sync_points_from_discord(bot))
    setup_modmail_events(bot)

    # 📈 株価自動更新タスクの開始 (重複実行防止)
    if not stock_price_update_task.is_running():
        stock_price_update_task.start(bot)

    # ------------------------------------------
    # 👑 1. 管理者専用 プレフィックスコマンド (!)
    # ------------------------------------------

    # --- !kabu コマンド (管理者専用 パネル) ---
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

    # --- !sendmessage (チャンネルID) (内容) コマンド (管理者専用) ---
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

    # --- /closereq コマンド ---
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

    # --- /close コマンド ---
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

    # --- /change_staff コマンド ---
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

    # --- /work コマンド ---
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

    # --- /points コマンド ---
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

    # --- /pointlog コマンド ---
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

    # --- /rankings コマンド ---
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

    # --- /give_points コマンド ---
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

    # --- /take_points コマンド ---
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

    # --- /kabu buy ---
    @kabu_group.command(name="buy", description="販売中の株式を購入します")
    async def kabu_buy(interaction: discord.Interaction):
        view = UserBuySelectView()
        if not view.children:
            await interaction.response.send_message("❌ 現在購入できる会社はありません。", ephemeral=True)
            return
        await interaction.response.send_message("🏢 購入したい会社を選択してください:", view=view, ephemeral=True)

    # --- /kabu sell ---
    @kabu_group.command(name="sell", description="保有している株式を売却します")
    async def kabu_sell(interaction: discord.Interaction):
        user_id_str = str(interaction.user.id)
        view = UserSellSelectView(user_id_str)
        if not view.children:
            await interaction.response.send_message("❌ 売却できる保有株がありません。", ephemeral=True)
            return
        await interaction.response.send_message("💸 売却したい会社を選択してください:", view=view, ephemeral=True)

    # --- /kabu company ---
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

    # --- /kabu info ---
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

    # Botツリーに `/kabu` グループを追加
    bot.tree.add_command(kabu_group)
