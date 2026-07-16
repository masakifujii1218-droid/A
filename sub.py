import discord
from discord import app_commands
import json
import os
import random
import asyncio
import io
from datetime import datetime

# ==========================================
# 設定エリア（ご指定のIDを設定しました！）
# ==========================================
# 👑 バックアップ専用チャンネルID
BACKUP_CHANNEL_ID = 1527164312634920980

# 📢 ポイントログ送信先チャンネルID
LOG_CHANNEL_ID_POINTS = 1526289865719943329

# 既存の設定
INBOX_CATEGORY_ID = 123456789012345678  # 問い合わせカテゴリID（必要に応じて変更してください）
LOG_CHANNEL_ID = 123456789012345678     # チケットログチャンネルID（必要に応じて変更してください）

# 🎯 権限ロールID
WORK_ROLE_ID = 1510021467155202057          # /work, /points, /pointlog を実行できるロールID
ADMIN_ROLE_ID_POINTS = 1510405214811852900  # 管理者（ポイント付与・消費操作ができる）ロールID

# ファイルパス
POINTS_FILE = "points.json"

# グローバル変数（インメモリバッファ）
points_cache = {}

# ==========================================
# データ管理・Discordバックアップコアシステム
# ==========================================

async def load_points_from_discord(bot):
    """
    起動時にDiscordのバックアップチャンネルから最新のJSONファイルをダウンロードし、
    ローカルの points.json を自動復元・同期します。
    """
    global points_cache
    channel = bot.get_channel(BACKUP_CHANNEL_ID)
    if not channel:
        print(f"⚠️ [バックアップ] ID {BACKUP_CHANNEL_ID} のチャンネルが見つかりません。ローカルファイルを読み込みます。")
        load_points_local()
        return

    print("🔄 [バックアップ] Discordのチャンネルから最新のポイントデータを探索中...")
    found_backup = False
    
    # チャンネルの履歴から最新の points.json を探索
    async for message in channel.history(limit=50):
        if message.attachments:
            for attachment in message.attachments:
                if attachment.filename == "points.json":
                    try:
                        file_bytes = await attachment.read()
                        points_cache = json.loads(file_bytes.decode("utf-8"))
                        
                        # ローカルに書き出して同期
                        with open(POINTS_FILE, "w", encoding="utf-8") as f:
                            json.dump(points_cache, f, ensure_ascii=False, indent=4)
                        
                        print(f"✅ [バックアップ] Discordからデータを正常に復元しました！ (メッセージID: {message.id})")
                        found_backup = True
                        break
                    except Exception as e:
                        print(f"❌ [バックアップ] データの読み込みに失敗しました: {e}")
            if found_backup:
                break

    if not found_backup:
        print("ℹ️ [バックアップ] Discord上に有効なデータが見つかりませんでした。ローカルの読み込みを試みます。")
        load_points_local()

def load_points_local():
    """ローカルファイルからデータをロード（フォールバック用）"""
    global points_cache
    if os.path.exists(POINTS_FILE):
        try:
            with open(POINTS_FILE, "r", encoding="utf-8") as f:
                points_cache = json.load(f)
                print("📁 [ローカル] points.json からデータを読み込みました。")
        except Exception as e:
            print(f"❌ [ローカル] 読み込み失敗、初期化します: {e}")
            points_cache = {}
    else:
        points_cache = {}

async def save_points_to_discord(bot):
    """
    ローカルの points.json を書き出し、同時にDiscordのバックアップチャンネルへ送信します。
    """
    global points_cache
    try:
        # 1. ローカルに保存
        with open(POINTS_FILE, "w", encoding="utf-8") as f:
            json.dump(points_cache, f, ensure_ascii=False, indent=4)
        
        # 2. Discordチャンネルへ送信
        channel = bot.get_channel(BACKUP_CHANNEL_ID)
        if channel:
            with open(POINTS_FILE, "rb") as f:
                discord_file = discord.File(f, filename="points.json")
                now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                await channel.send(
                    content=f"📦 **ポイントデータベース自動同期**\n保存日時: `{now_str}`\nユーザー数: `{len(points_cache)}名`",
                    file=discord_file
                )
            print("💾 [バックアップ] Discordへ最新データをアップロードしました！")
        else:
            print(f"⚠️ [バックアップ] 送信先チャンネル(ID: {BACKUP_CHANNEL_ID})が見つかりません。")
    except Exception as e:
        print(f"❌ [バックアップ] 保存・同期中にエラーが発生しました: {e}")

def get_user_data(user_id_str: str) -> dict:
    """ユーザーデータを取得、存在しなければ新規作成"""
    global points_cache
    if user_id_str not in points_cache:
        points_cache[user_id_str] = {
            "points": 0,
            "logs": []
        }
    if "points" not in points_cache[user_id_str]:
        points_cache[user_id_str]["points"] = 0
    if "logs" not in points_cache[user_id_str]:
        points_cache[user_id_str]["logs"] = []
    return points_cache[user_id_str]

async def update_user_data_async(bot, user_id_str: str, new_points: int, log_entry: str = None):
    """ユーザーデータを更新し、Discordへ非同期保存・同期します"""
    global points_cache
    user_data = get_user_data(user_id_str)
    user_data["points"] = new_points
    if log_entry:
        user_data["logs"].append(log_entry)
        if len(user_data["logs"]) > 100:
            user_data["logs"] = user_data["logs"][-100:] # 最大100件維持
    
    await save_points_to_discord(bot)

# ==========================================
# 外部接続用の初期設定関数 (メインファイルから呼ぶ用)
# ==========================================
async def setup_sub_system(bot):
    """起動時にメインから呼び出し、自動同期を開始します"""
    await load_points_from_discord(bot)

# ==========================================
# チケット管理Views & クイズクラス (すべて復元！)
# ==========================================

class StarRatingView(discord.ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=None)
        self.user_id = user_id

    @discord.ui.button(label="⭐1", style=discord.ButtonStyle.secondary, custom_id="rate_1")
    async def rate_1(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.process_rating(interaction, 1)

    @discord.ui.button(label="⭐2", style=discord.ButtonStyle.secondary, custom_id="rate_2")
    async def rate_2(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.process_rating(interaction, 2)

    @discord.ui.button(label="⭐3", style=discord.ButtonStyle.secondary, custom_id="rate_3")
    async def rate_3(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.process_rating(interaction, 3)

    @discord.ui.button(label="⭐4", style=discord.ButtonStyle.secondary, custom_id="rate_4")
    async def rate_4(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.process_rating(interaction, 4)

    @discord.ui.button(label="⭐5", style=discord.ButtonStyle.secondary, custom_id="rate_5")
    async def rate_5(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.process_rating(interaction, 5)

    async def process_rating(self, interaction: discord.Interaction, stars: int):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ あなたはこの問い合わせの当事者ではないため、評価できません。", ephemeral=True)
            return
        await interaction.response.send_message(f"💖 ご協力ありがとうございました！今回の対応を **⭐{stars}** で受け付けました。", ephemeral=True)
        self.stop()


class SupportClaimView(discord.ui.View):
    def __init__(self, user_id: int, user_name: str):
        super().__init__(timeout=None)
        self.user_id = user_id
        self.user_name = user_name

    @discord.ui.button(label="🙋‍♂️ 対応を担当する", style=discord.ButtonStyle.green, custom_id="claim_ticket_btn")
    async def claim_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = interaction.channel
        await channel.edit(name=f"担当-{interaction.user.name}", topic=f"User ID: {self.user_id} | Staff: {interaction.user.id}")
        
        embed = discord.Embed(
            title="🤝 担当者が決定しました",
            description=f"この問い合わせは {interaction.user.mention} が担当します。\nよろしくお願いいたします！",
            color=discord.Color.blue()
        )
        button.disabled = True
        await interaction.response.edit_message(view=self)
        await channel.send(embed=embed)


class QuizGameView(discord.ui.View):
    """クイズ用の三択・四択ボタンビュー"""
    def __init__(self, correct_idx: int, choices: list, question_id: str, bot_client):
        super().__init__(timeout=15.0)
        self.correct_idx = correct_idx
        self.choices = choices
        self.question_id = question_id
        self.bot_client = bot_client
        self.answered_users = set()

        for idx, choice in enumerate(choices):
            style = discord.ButtonStyle.secondary
            btn = discord.ui.Button(label=f"{idx+1}. {choice}", style=style, custom_id=f"quiz_choice_{idx}")
            btn.callback = self.make_callback(idx)
            self.add_item(btn)

    def make_callback(self, idx: int):
        async def callback(interaction: discord.Interaction):
            user_id_str = str(interaction.user.id)
            if user_id_str in self.answered_users:
                await interaction.response.send_message("❌ すでにこのクイズに回答しています！", ephemeral=True)
                return

            self.answered_users.add(user_id_str)

            if idx == self.correct_idx:
                user_data = get_user_data(user_id_str)
                new_points = user_data["points"] + 50
                now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
                log_entry = f"[{now_str}] 🪙 +50 pt (クイズ正解報酬)"
                await update_user_data_async(self.bot_client, user_id_str, new_points, log_entry)

                await interaction.response.send_message(
                    f"🎉 正解です！\nあなたの選んだ「{self.choices[idx]}」は正しい回答です！\n**50ポイント** 🪙 を獲得しました！ (現在の所持: `{new_points} pt`)",
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    f"❌ 残念、不正解です！\n正解は「{self.correct_idx+1}. {self.choices[self.correct_idx]}」でした。",
                    ephemeral=True
                )
        return callback

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        self.stop()

# ==========================================
# スラッシュコマンド（チケット＆ポイント統合）
# ==========================================

def setup_slash_commands(bot: discord.Client):
    """メイン側からすべてのコマンドを登録します"""

    # --- /create_ticket_panel (問い合わせパネル作成) ---
    @bot.tree.command(name="create_ticket_panel", description="問い合わせを開始するためのパネル（ボタン付きメッセージ）を設置します")
    async def create_ticket_panel_command(interaction: discord.Interaction):
        # 権限チェック
        if not any(role.id == ADMIN_ROLE_ID_POINTS for role in interaction.user.roles):
            embed = discord.Embed(description="❌ このコマンドを実行する権限がありません。", color=discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        embed = discord.Embed(
            title="📩 問い合わせ窓口",
            description="チケットを開いて、運営スタッフへの個別問い合わせチャネルを作成します。\n下のボタンをクリックして開始してください。",
            color=discord.Color.blue()
        )
        
        class CreateTicketView(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=None)
            
            @discord.ui.button(label="✉️ チケットを開く", style=discord.ButtonStyle.primary, custom_id="open_ticket_btn_main")
            async def open_ticket(self, press_interaction: discord.Interaction, button: discord.ui.Button):
                await press_interaction.response.send_message("🔄 チケットを開設しています...", ephemeral=True)
                
                guild = press_interaction.guild
                category = guild.get_channel(INBOX_CATEGORY_ID)
                
                overwrites = {
                    guild.default_role: discord.PermissionOverwrite(read_messages=False),
                    press_interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
                    guild.get_role(ADMIN_ROLE_ID_POINTS): discord.PermissionOverwrite(read_messages=True, send_messages=True)
                }
                
                channel_name = f"ticket-{press_interaction.user.name.lower()}"
                ticket_channel = await guild.create_text_channel(
                    name=channel_name,
                    category=category,
                    overwrites=overwrites,
                    topic=f"User ID: {press_interaction.user.id}"
                )
                
                claim_view = SupportClaimView(user_id=press_interaction.user.id, user_name=press_interaction.user.name)
                welcome_embed = discord.Embed(
                    title="🔔 チケットが開かれました",
                    description=f"{press_interaction.user.mention}さん、ようこそ。\nこちらにお問い合わせ内容をご記入ください。\n運営スタッフが対応するまで今しばらくお待ちください。",
                    color=discord.Color.green()
                )
                await ticket_channel.send(embed=welcome_embed, view=claim_view)
        
        await interaction.response.send_message("✅ 問い合わせパネルを作成しました。", ephemeral=True)
        await interaction.channel.send(embed=embed, view=CreateTicketView())

    # --- /close_ticket コマンド ---
    @bot.tree.command(name="close_ticket", description="【運営専用】この問い合わせチケットをクローズします")
    async def close_ticket_command(interaction: discord.Interaction):
        channel = interaction.channel
        if not channel.category or channel.category_id != INBOX_CATEGORY_ID:
            await interaction.response.send_message("❌ このチャンネルでは実行できません。", ephemeral=True)
            return

        await interaction.response.defer()

        # ユーザーIDの解析
        user = None
        if channel.topic and "User ID:" in channel.topic:
            try:
                parts = channel.topic.split("|")
                u_id = int(parts[0].replace("User ID:", "").strip())
                user = await interaction.client.fetch_user(u_id)
            except:
                pass

        # ログ作成
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
            except:
                pass

        await asyncio.sleep(2)
        await channel.delete()

    # --- /change_staff コマンド ---
    @bot.tree.command(name="change_staff", description="チケットの担当スタッフをリセットして交代します")
    async def change_staff_command(interaction: discord.Interaction):
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


    # --- /work コマンド (権限ロール確認付き) ---
    @bot.tree.command(name="work", description="毎日の仕事をこなしてポイントを獲得します")
    @app_commands.checks.cooldown(1, 28800, key=lambda i: i.user.id)
    async def work_command(interaction: discord.Interaction):
        # メンバー用のロールIDを持っているかチェック
        if not any(role.id == WORK_ROLE_ID for role in interaction.user.roles):
            embed = discord.Embed(description="❌ このコマンドを実行する権限（指定ロール）がありません。", color=discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        await interaction.response.defer(ephemeral=False)

        if random.random() < 0.70:
            earned = random.randint(200, 300)
        else:
            earned = random.choice([random.randint(50, 199), random.randint(301, 400)])

        user_id_str = str(interaction.user.id)
        user_data = get_user_data(user_id_str)
        new_points = user_data["points"] + earned
        
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        log_entry = f"[{now_str}] 🪙 +{earned} pt (お仕事報酬)"
        
        await update_user_data_async(bot, user_id_str, new_points, log_entry)

        embed = discord.Embed(
            title="💼 お仕事完了！",
            description=f"{interaction.user.mention}さんが仕事を完了しました。\n\n獲得: **{earned}** ポイント 🪙",
            color=discord.Color.green(),
            timestamp=datetime.now()
        )
        embed.add_field(name="現在の総保有", value=f"`{new_points} pt`")
        await interaction.followup.send(embed=embed)

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

    # --- /points コマンド (メンバー用ロールが必要) ---
    @bot.tree.command(name="points", description="指定したユーザー（または自分）の保有ポイントを確認します")
    async def points_command(interaction: discord.Interaction, ユーザー: discord.User = None):
        # メンバー用のロールIDを持っているかチェック
        if not any(role.id == WORK_ROLE_ID for role in interaction.user.roles):
            embed = discord.Embed(description="❌ このコマンドを実行する権限がありません。", color=discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        target_user = ユーザー or interaction.user
        user_data = get_user_data(str(target_user.id))

        embed = discord.Embed(
            title="🪙 ポイント確認",
            description=f"{target_user.mention} さんの現在の残高です。",
            color=discord.Color.gold(),
            timestamp=datetime.now()
        )
        embed.add_field(name="ポイント残高", value=f"**{user_data['points']}** pt", inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=False)

    # --- /pointlog コマンド (メンバー用ロールが必要) ---
    @bot.tree.command(name="pointlog", description="ポイントの利用履歴（通帳）を最大100件確認します")
    async def pointlog_command(interaction: discord.Interaction, ユーザー: discord.User = None):
        # メンバー用のロールIDを持っているかチェック
        if not any(role.id == WORK_ROLE_ID for role in interaction.user.roles):
            embed = discord.Embed(description="❌ このコマンドを実行する権限がありません。", color=discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        target_user = ユーザー or interaction.user
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

    # --- /give_points コマンド (管理者用ロールが必要) ---
    @bot.tree.command(name="give_points", description="【管理者専用】他人のポイントを増やします")
    async def give_points_command(interaction: discord.Interaction, ユーザー: discord.User, ポイント数: int, 理由: str):
        if not any(role.id == ADMIN_ROLE_ID_POINTS for role in interaction.user.roles):
            embed = discord.Embed(description="❌ このコマンドを実行する権限がありません。", color=discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        await interaction.response.defer(ephemeral=False)

        user_id_str = str(ユーザー.id)
        user_data = get_user_data(user_id_str)
        new_points = user_data["points"] + ポイント数
        
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        log_entry = f"[{now_str}] 🪙 +{ポイント数} pt (付与: {理由})"
        
        await update_user_data_async(bot, user_id_str, new_points, log_entry)

        res_embed = discord.Embed(
            title="✅ ポイント付与完了",
            description=f"{ユーザー.mention} に **{ポイント数}** ポイントを付与しました。\n理由: {理由}",
            color=discord.Color.green()
        )
        await interaction.followup.send(embed=res_embed)

        log_channel = interaction.client.get_channel(LOG_CHANNEL_ID_POINTS)
        if log_channel:
            noti_embed = discord.Embed(title="📥 ポイント変動通知 (付与)", color=discord.Color.green(), timestamp=datetime.now())
            noti_embed.add_field(name="対象者", value=ユーザー.mention, inline=True)
            noti_embed.add_field(name="対応者", value=interaction.user.mention, inline=True)
            noti_embed.add_field(name="変動値", value=f"+{ポイント数} pt", inline=True)
            noti_embed.add_field(name="理由", value=理由, inline=False)
            await log_channel.send(embed=noti_embed)

    # --- /take_points コマンド (管理者用ロールが必要) ---
    @bot.tree.command(name="take_points", description="【管理者専用】他人のポイントを消費・減算します")
    async def take_points_command(interaction: discord.Interaction, ユーザー: discord.User, ポイント数: int, 理由: str):
        if not any(role.id == ADMIN_ROLE_ID_POINTS for role in interaction.user.roles):
            embed = discord.Embed(description="❌ このコマンドを実行する権限がありません。", color=discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        await interaction.response.defer(ephemeral=False)

        user_id_str = str(ユーザー.id)
        user_data = get_user_data(user_id_str)
        new_points = user_data["points"] - ポイント数
        
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        log_entry = f"[{now_str}] 💸 -{ポイント数} pt (消費: {理由})"
        
        await update_user_data_async(bot, user_id_str, new_points, log_entry)

        res_embed = discord.Embed(
            title="⚠️ ポイント消費",
            description=f"{ユーザー.mention} のポイントを **{ポイント数}** 消費しました。\n目的・理由: {理由}",
            color=discord.Color.orange()
        )
        await interaction.followup.send(embed=res_embed)

        log_channel = interaction.client.get_channel(LOG_CHANNEL_ID_POINTS)
        if log_channel:
            noti_embed = discord.Embed(title="📤 ポイント変動通知 (消費)", color=discord.Color.red(), timestamp=datetime.now())
            noti_embed.add_field(name="対象者", value=ユーザー.mention, inline=True)
            noti_embed.add_field(name="対応者", value=interaction.user.mention, inline=True)
            noti_embed.add_field(name="変動値", value=f"-{ポイント数} pt", inline=True)
            noti_embed.add_field(name="使用用途（理由）", value=理由, inline=False)
            await log_channel.send(embed=noti_embed)
