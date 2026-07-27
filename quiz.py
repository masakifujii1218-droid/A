import discord
from discord.ext import commands
import json
import os
import asyncio

# ==========================================
# 永続化用チャンネル・メッセージ管理
# ==========================================
CONFIG_CHANNEL_ID = 1344265089330860124  # 設定保存用チャンネルID
config_message_id = None

# 初期設定データ構造
quiz_config = {
    "is_open": True,
    "panel_channel_id": None,
    "panel_message_id": None,
    "admin_channel_id": None,
    "admin_message_id": None,
    "role_name": "自己推薦",  # チャンネル名に使用する役職名・種別名
    "questions": [
        {
            "id": 1,
            "question": "志望動機・自己PRを教えてください。"
        },
        {
            "id": 2,
            "question": "得意なことやアピールしたい活動実績を教えてください。"
        }
    ]
}

async def save_config_to_discord(bot: commands.Bot):
    """設定データを指定のチャンネルに保存する"""
    global config_message_id
    channel = bot.get_channel(CONFIG_CHANNEL_ID)
    if not channel:
        print(f"❌ 設定保存用チャンネル (ID: {CONFIG_CHANNEL_ID}) が見つかりません。")
        return

    content = f"```json\n{json.dumps(quiz_config, ensure_ascii=False, indent=2)}\n```"

    try:
        if config_message_id:
            try:
                msg = await channel.fetch_message(config_message_id)
                await msg.edit(content=content)
                return
            except discord.NotFound:
                pass
        
        msg = await channel.send(content=content)
        config_message_id = msg.id
        print("✅ quiz.py の設定データをDiscordに保存しました。")
    except Exception as e:
        print(f"❌ quiz.py 設定保存エラー: {e}")

async def load_config_from_discord(bot: commands.Bot):
    """起動時にDiscordから設定データを読み込む"""
    global config_message_id, quiz_config
    channel = bot.get_channel(CONFIG_CHANNEL_ID)
    if not channel:
        print(f"⚠️ 設定保存用チャンネル (ID: {CONFIG_CHANNEL_ID}) が見つかりませんでした。初期値で動作します。")
        return

    try:
        async for msg in channel.history(limit=10):
            if msg.author.id == bot.user.id and msg.content.startswith("```json"):
                json_str = msg.content.strip("`").replace("json\n", "").strip()
                quiz_config.update(json.loads(json_str))
                config_message_id = msg.id
                print("✅ quiz.py の設定データをDiscordから正常に復旧しました。")
                break
    except Exception as e:
        print(f"❌ quiz.py 設定復旧エラー: {e}")

# ==========================================
# 1問ずつメッセージで出題・回答を受付する処理
# ==========================================
async def start_quiz_session(channel: discord.TextChannel, applicant: discord.Member, bot: commands.Bot):
    questions = quiz_config.get("questions", [])
    answers = []

    def check(m: discord.Message):
        # 応募者本人が該当チャンネルで送信したメッセージのみを受け付ける
        return m.author.id == applicant.id and m.channel.id == channel.id

    for q in questions:
        embed = discord.Embed(
            title=f"❓ 質問 {q['id']} / {len(questions)}",
            description=q["question"],
            color=discord.Color.blue()
        )
        embed.set_footer(text="このチャンネルにメッセージを送信して回答してください。")
        await channel.send(embed=embed)

        try:
            # ユーザーからのメッセージ応答を待つ (タイムアウト: 30分)
            msg = await bot.wait_for("message", check=check, timeout=1800.0)
            answers.append({
                "question": q["question"],
                "answer": msg.content
            })
            await channel.send("✅ 回答を受け付けました。")
            await asyncio.sleep(1)
        except asyncio.TimeoutError:
            await channel.send("⏰ 応答が一定時間なかったため、受付を一時中断しました。")
            return

    # 全問回答完了時の結果出力
    result_embed = discord.Embed(
        title="📄 応募回答が提出されました",
        description="ご回答ありがとうございました！審査完了までお待ちください。",
        color=discord.Color.green()
    )
    result_embed.set_author(name=f"{applicant.display_name} ({applicant.name})", icon_url=applicant.display_avatar.url)

    for idx, item in enumerate(answers, 1):
        result_embed.add_field(
            name=f"問{idx}. {item['question']}",
            value=item["answer"],
            inline=False
        )
    result_embed.set_footer(text=f"User ID: {applicant.id}")

    await channel.send(embed=result_embed)

# ==========================================
# 準備確認ボタン View (チケット作成後に送信)
# ==========================================
class ReadyCheckView(discord.ui.View):
    def __init__(self, applicant: discord.Member):
        super().__init__(timeout=None)
        self.applicant = applicant

    @discord.ui.button(label="はい (開始する)", style=discord.ButtonStyle.success, custom_id="quiz_ready_yes")
    async def ready_yes(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.applicant.id:
            await interaction.response.send_message("⚠️ 応募者本人しか操作できません。", ephemeral=True)
            return

        button.disabled = True
        await interaction.response.edit_message(content="👍 準備完了ですね！それでは質問を開始します。", view=None)

        # 質疑応答セッション開始
        await start_quiz_session(interaction.channel, self.applicant, interaction.client)

# ==========================================
# 応募ボタン View (一般ユーザー用パネル)
# ==========================================
class QuizUserPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="📝 応募する", style=discord.ButtonStyle.primary, custom_id="quiz_apply_button")
    async def apply_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not quiz_config.get("is_open", True):
            await interaction.response.send_message("🚫 現在、募集は締め切られています。", ephemeral=True)
            return

        guild = interaction.guild
        user = interaction.user
        role_name = quiz_config.get("role_name", "自己推薦")

        # チャンネル名: 「(応募役職)-(ユーザー名)」
        channel_name = f"{role_name}-{user.name}".lower()

        # 権限設定（非公開チャンネル）
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)
        }

        # チャンネル作成
        category = interaction.channel.category
        ticket_channel = await guild.create_text_channel(
            name=channel_name,
            category=category,
            overwrites=overwrites,
            topic=f"{user.display_name} さんの応募用チケットチャンネルです。"
        )

        # チケットチャンネル内で「準備はできましたか？」と確認
        ready_embed = discord.Embed(
            title=f"📋 {role_name} 応募手続き",
            description=f"{user.mention} さん、専用チャンネルを作成しました。\n\n**準備はできましたか？**\n以下の「はい (開始する)」ボタンを押すと質問を開始します。",
            color=discord.Color.green()
        )
        view = ReadyCheckView(applicant=user)
        await ticket_channel.send(content=user.mention, embed=ready_embed, view=view)

        # 本人への案内メッセージ
        await interaction.response.send_message(f"✅ 専用チャンネルを作成しました: {ticket_channel.mention}", ephemeral=True)

# ==========================================
# 管理パネル View (管理者用)
# ==========================================
class AdminPanelEditView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="📌 応募パネルをここに設置", style=discord.ButtonStyle.success, custom_id="quiz_setup_panel")
    async def setup_panel(self, interaction: discord.Interaction, button: discord.ui.Button):
        status_text = "🟢 **現在募集受付中**" if quiz_config.get("is_open", True) else "🔴 **現在募集停止中**"
        
        embed = discord.Embed(
            title="✨ 自己推薦・応募受付",
            description=f"以下のボタンを押すと専用の応募用チャンネルが作成されます。\n\n**ステータス:** {status_text}",
            color=discord.Color.green() if quiz_config.get("is_open", True) else discord.Color.red()
        )
        
        view = QuizUserPanelView()
        msg = await interaction.channel.send(embed=embed, view=view)
        
        quiz_config["panel_channel_id"] = interaction.channel.id
        quiz_config["panel_message_id"] = msg.id
        await save_config_to_discord(interaction.client)
        
        await interaction.response.send_message("✅ 応募パネルを設置しました！", ephemeral=True)

    @discord.ui.button(label="🔄 募集ON/OFF切替", style=discord.ButtonStyle.secondary, custom_id="quiz_toggle_status")
    async def toggle_status(self, interaction: discord.Interaction, button: discord.ui.Button):
        current = quiz_config.get("is_open", True)
        quiz_config["is_open"] = not current
        await save_config_to_discord(interaction.client)

        status_str = "🟢 **募集を開始**" if quiz_config["is_open"] else "🔴 **募集を停止**"
        await interaction.response.send_message(f"ステータスを変更しました: {status_str}", ephemeral=True)

# ==========================================
# コマンドの登録関数
# ==========================================
def setup_quiz_commands(bot: commands.Bot):

    @bot.command(name="recommendadminpanel")
    @commands.has_permissions(administrator=True)
    async def recommend_admin_panel(ctx: commands.Context):
        """管理パネルを設置するコマンド"""
        embed = discord.Embed(
            title="⚙️ 自己推薦 システム管理パネル",
            description="下のボタンから応募パネルの設置や募集の切り替えを行えます。",
            color=discord.Color.gold()
        )
        view = AdminPanelEditView()
        msg = await ctx.send(embed=embed, view=view)
        quiz_config["admin_channel_id"] = ctx.channel.id
        quiz_config["admin_message_id"] = msg.id
        await save_config_to_discord(bot)

    @bot.command(name="recommendpanel")
    @commands.has_permissions(administrator=True)
    async def recommend_panel(ctx: commands.Context):
        """応募パネルを直接設置するコマンド"""
        status_text = "🟢 **現在募集受付中**" if quiz_config.get("is_open", True) else "🔴 **現在募集停止中**"
        embed = discord.Embed(
            title="✨ 自己推薦・応募受付",
            description=f"以下のボタンを押すと専用の応募用チャンネルが作成されます。\n\n**ステータス:** {status_text}",
            color=discord.Color.green() if quiz_config.get("is_open", True) else discord.Color.red()
        )
        view = QuizUserPanelView()
        msg = await ctx.send(embed=embed, view=view)
        quiz_config["panel_channel_id"] = ctx.channel.id
        quiz_config["panel_message_id"] = msg.id
        await save_config_to_discord(bot)
