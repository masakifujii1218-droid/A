# ==========================================
# sub.py (Modmailシステム + 1時間自動同期・復元付きポイントシステム)
# ==========================================
import discord
from discord.ext import commands, tasks  # tasksを追加
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

VERSION = "v7.0.0 (Modmail + Hourly Sync Point System)"

# --- ポイントシステム用設定 ---
LOG_CHANNEL_ID_POINTS = 1526289865719943329  # ポイント通知用チャンネルID
WORK_ROLE_ID = 1510021467155202057           # /work を実行できるロールID
ADMIN_ROLE_ID_POINTS = 1510405214811852900    # 管理者ロールID

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
POINTS_FILE = os.path.join(BASE_DIR, "points.json")
# 🌟 Renderの再起動対策：1時間ごとにデータを逃がしておく秘密の同期ファイル
BACKUP_FILE = os.path.join(BASE_DIR, "points_hourly_sync.json")

points_data = {}

# ==========================================
# ポイントデータ管理関数 (1時間自動同期・復元対応)
# ==========================================
def load_points():
    global points_data
    
    # 1. 通常のデータファイルがあれば最優先で読み込む
    if os.path.exists(POINTS_FILE):
        try:
            with open(POINTS_FILE, "r", encoding="utf-8") as f:
                points_data = json.load(f)
                print("【システム】通常のポイントデータを読み込みました。")
                return
        except Exception as e:
            print(f"データ読み込み失敗: {e}")

    # 2. 【最重要】Renderの再起動等でpoints.jsonが消えていた場合、1時間前の同期ファイルから自動復元
    if os.path.exists(BACKUP_FILE):
        try:
            with open(BACKUP_FILE, "r", encoding="utf-8") as f:
                points_data = json.load(f)
                print("⚠️【警告】データが消失していたため、1時間前の同期データから自動復元しました！")
                save_points()  # 復元したデータを通常ファイルとして保存
                return
        except Exception as e:
            print(f"バックアップからの復元失敗: {e}")

    # 3. どちらもなければ新規作成
    points_data = {}
    print("【システム】新規ポイントデータを作成しました。")

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
# 🕒 1時間ごとにポイントを同期（固定）するループタスク
# ==========================================
@tasks.loop(hours=1)
async def sync_points_hourly():
    global points_data
    try:
        with open(BACKUP_FILE, "w", encoding="utf-8") as f:
            json.dump(points_data, f, ensure_ascii=False, indent=4)
        print(f"🕒【同期完了】現在のポイント数を1時間前として固定しました ({datetime.now().strftime('%H:%M')})")
    except Exception as e:
        print(f"定期同期失敗: {e}")


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


# ==========================================
# 管理・一般コマンド (各種スラッシュコマンド)
# ==========================================
def setup_admin_commands(bot: commands.Bot):
    setup_modmail_events(bot)

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


    # ==========================================
    # ポイントシステム スラッシュコマンド (通常版)
    # ==========================================

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
    async def points_command(interaction: discord.Interaction, ユーザー: discord.User = None):
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

    # --- /pointlog コマンド ---
    @bot.tree.command(name="pointlog", description="ポイントの利用履歴（通帳）を最大100件確認します")
    async def pointlog_command(interaction: discord.Interaction, ユーザー: discord.User = None):
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

    # --- /give_points コマンド ---
    @bot.tree.command(name="give_points", description="【管理者専用】他人のポイントを増やします")
    async def give_points_command(interaction: discord.Interaction, ユーザー: discord.User, ポイント数: int, 理由: str):
        if not any(role.id == ADMIN_ROLE_ID_POINTS for role in interaction.user.roles):
            embed = discord.Embed(description="❌ このコマンドを実行する権限がありません。", color=discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=False)
            return

        user_id_str = str(ユーザー.id)
        user_data = get_user_data(user_id_str)
        new_points = user_data["points"] + ポイント数
        
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        log_entry = f"[{now_str}] 🪙 +{ポイント数} pt (付与: {理由})"
        
        update_user_data(user_id_str, new_points, log_entry)

        res_embed = discord.Embed(
            title="✅ ポイント付与完了",
            description=f"{ユーザー.mention} に **{ポイント数}** ポイントを付与しました。\n理由: {理由}",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=res_embed, ephemeral=False)

        log_channel = interaction.client.get_channel(LOG_CHANNEL_ID_POINTS)
        if log_channel:
            noti_embed = discord.Embed(title="📥 ポイント変動通知 (付与)", color=discord.Color.green(), timestamp=datetime.now())
            noti_embed.add_field(name="対象者", value=ユーザー.mention, inline=True)
            noti_embed.add_field(name="対応者", value=interaction.user.mention, inline=True)
            noti_embed.add_field(name="変動値", value=f"+{ポイント数} pt", inline=True)
            noti_embed.add_field(name="理由", value=理由, inline=False)
            await log_channel.send(embed=noti_embed)

    # --- /take_points コマンド ---
    @bot.tree.command(name="take_points", description="【管理者専用】他人のポイントを消費・減算します")
    async def take_points_command(interaction: discord.Interaction, ユーザー: discord.User, ポイント数: int, 理由: str):
        if not any(role.id == ADMIN_ROLE_ID_POINTS for role in interaction.user.roles):
            embed = discord.Embed(description="❌ このコマンドを実行する権限がありません。", color=discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=False)
            return

        user_id_str = str(ユーザー.id)
        user_data = get_user_data(user_id_str)
        new_points = user_data["points"] - ポイント数
        
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        log_entry = f"[{now_str}] 💸 -{ポイント数} pt (消費: {理由})"
        
        update_user_data(user_id_str, new_points, log_entry)

        res_embed = discord.Embed(
            title="⚠️ ポイント消費",
            description=f"{ユーザー.mention} のポイントを **{ポイント数}** 消費しました。\n目的・理由: {理由}",
            color=discord.Color.orange()
        )
        await interaction.response.send_message(embed=res_embed, ephemeral=False)

        log_channel = interaction.client.get_channel(LOG_CHANNEL_ID_POINTS)
        if log_channel:
            noti_embed = discord.Embed(title="📤 ポイント変動通知 (消費)", color=discord.Color.red(), timestamp=datetime.now())
            noti_embed.add_field(name="対象者", value=ユーザー.mention, inline=True)
            noti_embed.add_field(name="対応者", value=interaction.user.mention, inline=True)
            noti_embed.add_field(name="変動値", value=f"-{ポイント数} pt", inline=True)
            noti_embed.add_field(name="使用用途（理由）", value=理由, inline=False)
            await log_channel.send(embed=noti_embed)