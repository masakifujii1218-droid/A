# ==========================================
# sub.py (Modmailシステム + 権限自動付与 ＆ クローズリクエスト)
# ==========================================
import discord
from discord.ext import commands
import asyncio
from datetime import datetime
import io

# --- 固定設定 ---
INBOX_CATEGORY_ID = 1513901626610553043   # 問い合わせが入るカテゴリー
LOG_CHANNEL_ID = 1510042822533840936      # ログが送信されるチャンネル
RATING_CHANNEL_ID = 1510639675239432313   # ★評価と改善点が届くチャンネル
ADMIN_ROLE_ID = 1510021467167789104       # 運営・管理者ロールID（自動権限付与用）

VERSION = "v3.6.0 (Auto-Permission & Closereq)"

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
                description=f"**対象ユーザー:** <@{self.user_id}>\n**クローズ方式:** ユーザー同意によるクローズ (`?closereq`)",
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
                
                # --- 【権限問題の完全自動解決】 ---
                staff_role = guild.get_role(ADMIN_ROLE_ID)
                overwrites = {
                    guild.default_role: discord.PermissionOverwrite(read_messages=False),
                    guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
                }
                # 指定した管理・スタッフロールに最初から閲覧権限を付与
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
            if message.content.startswith("?"): return
            if not message.channel.topic or "User ID:" not in message.channel.topic: return

            try:
                parts = message.channel.topic.split("|")
                u_id = int(parts[0].replace("User ID:", "").strip())
                user = await bot.fetch_user(u_id)
            except: return

            staff_embed = discord.Embed(description=message.content, color=discord.Color.blue())
            staff_embed.set_author(name="サーバー運営チーム (返信)", icon_url=message.guild.icon.url if message.guild.icon else None)
            try:
                await user.send(embed=staff_embed)
                await message.add_reaction("✈️")
            except discord.Forbidden:
                await message.channel.send("❌ ユーザーのDMが閉じられているため転送できませんでした。")


# ==========================================
# コマンドのセットアップ
# ==========================================
def setup_admin_commands(bot: commands.Bot):
    setup_modmail_events(bot)

    @bot.command(name="closereq")
    async def close_request(ctx: commands.Context):
        if not ctx.channel.category or ctx.channel.category_id != INBOX_CATEGORY_ID: return
        if not ctx.channel.topic or "User ID:" not in ctx.channel.topic: return

        try:
            parts = ctx.channel.topic.split("|")
            u_id = int(parts[0].replace("User ID:", "").strip())
            user = await bot.fetch_user(u_id)
        except:
            await ctx.send("❌ ユーザー情報を取得できませんでした。")
            return

        await ctx.send(f"📬 {user.mention} のDMへクローズ確認リクエストを送信しました。")

        req_embed = discord.Embed(
            title="🔒 問い合わせ終了の確認",
            description=f"スタッフ（{ctx.author.mention}）より、この問い合わせを終了（クローズ）して良いかの確認が届きました。\n\n問題が解決し、チケットを閉じてよろしければ、下の**「閉じる」**ボタンを押してください。",
            color=discord.Color.yellow()
        )
        view = CloseRequestConfirmView(
            channel_id=ctx.channel.id, user_id=user.id, channel_name=ctx.channel.name, staff_mention=ctx.author.mention
        )
        try:
            await user.send(embed=req_embed, view=view)
        except discord.Forbidden:
            await ctx.send("❌ ユーザーのDMが閉じられているため、リクエストを送信できませんでした。")

    @bot.command(name="close")
    async def close_ticket(ctx: commands.Context):
        if not ctx.channel.category or ctx.channel.category_id != INBOX_CATEGORY_ID: return
        if not ctx.channel.topic or "User ID:" not in ctx.channel.topic: return

        await ctx.send("🔒 強制クローズ処理中...")

        try:
            parts = ctx.channel.topic.split("|")
            u_id = int(parts[0].replace("User ID:", "").strip())
            user = await bot.fetch_user(u_id)
        except: user = None

        log_lines = []
        async for msg in ctx.channel.history(limit=100, oldest_first=True):
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
                title=f"🔒 チケットクローズログ: {ctx.channel.name}",
                description=f"**対象ユーザー:** {user.mention if user else ctx.channel.name}\n**クローズ実行者:** {ctx.author.mention} (強制クローズ)",
                color=discord.Color.red(), timestamp=datetime.now()
            )
            if len(full_log_text) > 3000 or len(full_log_text) == 0:
                with io.StringIO(full_log_text) as f:
                    file = discord.File(f, filename=f"log-{ctx.channel.name}.txt")
                    await log_channel.send(embed=log_embed, file=file)
            else:
                log_embed.add_field(name="📜 やり取り内容", value=f"```\n{full_log_text}\n```", inline=False)
                await log_channel.send(embed=log_embed)

        if user:
            try:
                end_embed = discord.Embed(title="🔒 問い合わせクローズ", description="運営スタッフによりチケットが閉じられました。", color=discord.Color.red())
                await user.send(embed=end_embed)
            except: pass

        await asyncio.sleep(2)
        await ctx.channel.delete()

    @bot.command(name="change")
    async def change_staff(ctx: commands.Context, sub_cmd: str = None):
        if sub_cmd != "staff": return
        if not ctx.channel.category or ctx.channel.category_id != INBOX_CATEGORY_ID: return
        if not ctx.channel.topic or "User ID:" not in ctx.channel.topic: return

        try:
            parts = ctx.channel.topic.split("|")
            u_id = int(parts[0].replace("User ID:", "").strip())
            user = await bot.fetch_user(u_id)
        except:
            await ctx.send("❌ ユーザー情報の解析に失敗しました。")
            return

        await ctx.channel.edit(name=f"{user.name.lower()}", topic=f"User ID: {user.id}")
        new_view = SupportClaimView(user_id=user.id, user_name=user.name)
        reset_embed = discord.Embed(description="🔄 担当者がリセットされました。下のボタンを押して担当を交代してください。", color=discord.Color.yellow())
        await ctx.send(embed=reset_embed, view=new_view)