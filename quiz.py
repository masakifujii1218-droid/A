import discord
from discord.ext import commands
import json
import os
import asyncio

# ==========================================
# 永続化用チャンネル・メッセージ管理
# ==========================================
CONFIG_CHANNEL_ID = 1526289865719943329  # 設定保存用チャンネルID
config_message_id = None

# 初期設定データ構造
quiz_config = {
    "admin_channel_id": None,
    "admin_message_id": None,
    "departments": {
        "ダイヤ作成部": {
            "is_open": True,
            "questions": [
                {"id": 1, "question": "志望動機・自己PRを教えてください。"},
                {"id": 2, "question": "得意なことやアピールしたい活動実績を教えてください。"}
            ]
        }
    }
}

async def get_config_channel(bot: commands.Bot):
    """設定保存用チャンネルを取得する（キャッシュにない場合はAPIから直接取得）"""
    channel = bot.get_channel(CONFIG_CHANNEL_ID)
    if channel is None:
        try:
            channel = await bot.fetch_channel(CONFIG_CHANNEL_ID)
        except Exception as e:
            print(f"❌ [Quiz] 設定保存用チャンネル (ID: {CONFIG_CHANNEL_ID}) の取得に失敗しました: {e}")
            return None
    return channel

async def save_config_to_discord(bot: commands.Bot):
    """設定データを指定のチャンネルに自動保存・更新する"""
    global config_message_id
    print("🚀 [Quiz] データ保存処理 (save_config_to_discord) を開始します...")
    
    channel = await get_config_channel(bot)
    if not channel:
        print(f"❌ [Quiz] 保存用チャンネルが見つからないため保存を中断しました。")
        return

    content = f"```json\n{json.dumps(quiz_config, ensure_ascii=False, indent=2)}\n```"
    try:
        if config_message_id:
            try:
                msg = await channel.fetch_message(config_message_id)
                await msg.edit(content=content)
                print("✅ [Quiz] 設定データをDiscord上で更新しました。")
                return
            except discord.NotFound:
                print("⚠️ [Quiz] 保存用メッセージが見つかりませんでした。新規作成します。")
            except Exception as e:
                print(f"⚠️ [Quiz] メッセージ編集失敗: {e}")
        
        msg = await channel.send(content=content)
        config_message_id = msg.id
        print(f"✅ [Quiz] 設定データをDiscordに新規保存しました。(Message ID: {config_message_id})")
    except Exception as e:
        print(f"❌ [Quiz] 設定保存エラー: {e}")

async def load_config_from_discord(bot: commands.Bot):
    """起動時にDiscordから設定データを読み込む"""
    global config_message_id, quiz_config
    print("🔄 [Quiz] Discordから設定データの復旧を開始します...")
    
    channel = await get_config_channel(bot)
    if not channel:
        print(f"⚠️ [Quiz] 設定保存用チャンネルが見つかりませんでした。初期値で動作します。")
        return

    try:
        async for msg in channel.history(limit=10):
            if msg.author.id == bot.user.id and msg.content.startswith("```json"):
                json_str = msg.content.strip("`").replace("json\n", "").strip()
                loaded_data = json.loads(json_str)
                if "departments" in loaded_data:
                    quiz_config.update(loaded_data)
                config_message_id = msg.id
                print(f"✅ [Quiz] 設定データをDiscordから正常に復旧しました。(Message ID: {config_message_id})")
                return
        print("ℹ️ [Quiz] 保存されている設定データが見つかりませんでした。")
    except Exception as e:
        print(f"❌ [Quiz] 設定復旧エラー: {e}")

def generate_admin_embed():
    embed = discord.Embed(
        title="⚙️ 自己推薦 システム管理者パネル",
        color=discord.Color.gold()
    )
    
    dept_text = "【現在の部署一覧】\n"
    departments = quiz_config.get("departments", {})
    
    if not departments:
        dept_text += "現在登録されている部署はありません。\n"
    else:
        for dept, data in departments.items():
            status = "🟢" if data["is_open"] else "🔴"
            q_count = len(data["questions"])
            dept_text += f"・{dept}: {status} (質問{q_count}個)\n"
            
    dept_text += "\n下のボタンから部署の追加・削除・質問設定・ON/OFF切替が行えます。"
    embed.description = dept_text
    return embed

async def start_quiz_session(channel: discord.TextChannel, applicant: discord.Member, bot: commands.Bot, dept_name: str, questions: list):
    answers = []

    def check(m: discord.Message):
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

    result_embed = discord.Embed(
        title="📄 応募回答が提出されました",
        description=f"**応募部署: {dept_name}**\nご回答ありがとうございました！審査完了までお待ちください。",
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

class ReadyCheckView(discord.ui.View):
    def __init__(self, applicant: discord.Member, dept_name: str, questions: list):
        super().__init__(timeout=None)
        self.applicant = applicant
        self.dept_name = dept_name
        self.questions = questions

    @discord.ui.button(label="はい (開始する)", style=discord.ButtonStyle.success, custom_id="quiz_ready_yes_persistent")
    async def ready_yes(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.applicant.id:
            await interaction.response.send_message("⚠️ 応募者本人しか操作できません。", ephemeral=True)
            return

        button.disabled = True
        await interaction.response.edit_message(content="👍 準備完了ですね！それでは質問を開始します。", view=None)
        await start_quiz_session(interaction.channel, self.applicant, interaction.client, self.dept_name, self.questions)

class QuizUserPanelSelect(discord.ui.Select):
    def __init__(self):
        options = []
        for dept, data in quiz_config.get("departments", {}).items():
            desc = "🟢 受付中" if data["is_open"] else "🔴 停止中"
            options.append(discord.SelectOption(label=dept, description=desc, value=dept))
            
        if not options:
            options.append(discord.SelectOption(label="現在募集中の部署はありません", value="none"))
            
        super().__init__(placeholder="応募する部署を選択してください...", min_values=1, max_values=1, options=options, custom_id="quiz_user_select_persistent")

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        dept_name = self.values[0]
        if dept_name == "none":
            await interaction.followup.send("現在応募できる部署がありません。", ephemeral=True)
            return

        dept_data = quiz_config["departments"].get(dept_name)
        if not dept_data or not dept_data["is_open"]:
            await interaction.followup.send(f"🚫 「{dept_name}」は存在しないか、現在募集を締め切っています。", ephemeral=True)
            return

        guild = interaction.guild
        user = interaction.user
        channel_name = f"{dept_name}-{user.name}".lower()

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)
        }

        category = interaction.channel.category
        ticket_channel = await guild.create_text_channel(
            name=channel_name,
            category=category,
            overwrites=overwrites,
            topic=f"{user.display_name} さんの【{dept_name}】応募用チャンネルです。"
        )

        ready_embed = discord.Embed(
            title=f"📋 {dept_name} 応募手続き",
            description=f"{user.mention} さん、専用チャンネルを作成しました。\n\n**準備はできましたか？**\n以下の「はい (開始する)」ボタンを押すと質問を開始します。",
            color=discord.Color.green()
        )
        view = ReadyCheckView(applicant=user, dept_name=dept_name, questions=dept_data["questions"])
        await ticket_channel.send(content=user.mention, embed=ready_embed, view=view)

        await interaction.followup.send(f"✅ {dept_name}の専用チャンネルを作成しました: {ticket_channel.mention}", ephemeral=True)

class QuizUserPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(QuizUserPanelSelect())

class AddDeptModal(discord.ui.Modal, title="新しい部署の追加"):
    dept_name = discord.ui.TextInput(label="部署名を入力", placeholder="例: 広報部", required=True, max_length=20)

    def __init__(self, admin_msg: discord.Message, bot_ref: commands.Bot):
        super().__init__()
        self.admin_msg = admin_msg
        self.bot_ref = bot_ref

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        name = self.dept_name.value
        if name in quiz_config["departments"]:
            await interaction.followup.send("⚠️ その部署は既に存在します。", ephemeral=True)
            return
            
        quiz_config["departments"][name] = {"is_open": True, "questions": []}
        await save_config_to_discord(self.bot_ref)
        try:
            await self.admin_msg.edit(embed=generate_admin_embed())
        except discord.NotFound:
            pass
        await interaction.followup.send(f"✅ 部署「{name}」を追加しました。", ephemeral=True)

class AddQuestionsModal(discord.ui.Modal):
    questions_text = discord.ui.TextInput(
        label="質問内容（1行につき1問）",
        style=discord.TextStyle.paragraph,
        placeholder="例:\n志望動機を教えてください\n得意な言語は何ですか\n過去の制作実績はありますか",
        required=True,
        max_length=2000
    )

    def __init__(self, dept_name: str, admin_msg: discord.Message, bot_ref: commands.Bot):
        super().__init__(title=f"{dept_name}に質問を一括追加")
        self.dept_name = dept_name
        self.admin_msg = admin_msg
        self.bot_ref = bot_ref

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        dept_data = quiz_config["departments"].get(self.dept_name)
        if not dept_data:
            await interaction.followup.send("⚠️ 指定された部署が見つかりませんでした。", ephemeral=True)
            return

        lines = [line.strip() for line in self.questions_text.value.split("\n") if line.strip()]
        current_len = len(dept_data["questions"])
        added_count = 0
        for i, line in enumerate(lines):
            new_id = current_len + i + 1
            dept_data["questions"].append({"id": new_id, "question": line})
            added_count += 1

        await save_config_to_discord(self.bot_ref)
        try:
            await self.admin_msg.edit(embed=generate_admin_embed())
        except discord.NotFound:
            pass
            
        await interaction.followup.send(f"✅ 「{self.dept_name}」に **{added_count}問** の質問を追加しました！", ephemeral=True)

class SelectDeptView(discord.ui.View):
    def __init__(self, action: str, admin_msg: discord.Message, bot_ref: commands.Bot):
        super().__init__(timeout=60)
        self.action = action
        self.admin_msg = admin_msg
        self.bot_ref = bot_ref
        
        options = [discord.SelectOption(label=d, value=d) for d in quiz_config["departments"].keys()]
        if not options:
            options.append(discord.SelectOption(label="部署がありません", value="none"))
            
        select = discord.ui.Select(placeholder="対象の部署を選択してください...", options=options)
        select.callback = self.select_callback
        self.add_item(select)

    async def select_callback(self, interaction: discord.Interaction):
        dept = self.children[0].values[0]
        if dept == "none":
            await interaction.response.edit_message(content="部署が存在しません。", view=None)
            return
        
        if self.action == "delete":
            await interaction.response.defer()
            del quiz_config["departments"][dept]
            await save_config_to_discord(self.bot_ref)
            try:
                await self.admin_msg.edit(embed=generate_admin_embed())
            except discord.NotFound:
                pass
            await interaction.edit_original_response(content=f"🗑️ 部署「{dept}」を削除しました。", view=None)
            
        elif self.action == "toggle":
            await interaction.response.defer()
            quiz_config["departments"][dept]["is_open"] = not quiz_config["departments"][dept]["is_open"]
            await save_config_to_discord(self.bot_ref)
            try:
                await self.admin_msg.edit(embed=generate_admin_embed())
            except discord.NotFound:
                pass
            state = "🟢 募集開始" if quiz_config["departments"][dept]["is_open"] else "🔴 募集停止"
            await interaction.edit_original_response(content=f"🔄 「{dept}」を **{state}** に変更しました。", view=None)
            
        elif self.action == "add_question":
            await interaction.response.send_modal(AddQuestionsModal(dept, self.admin_msg, self.bot_ref))
            try:
                await interaction.message.delete()
            except discord.NotFound:
                pass

class AdminPanelEditView(discord.ui.View):
    def __init__(self, bot_ref: commands.Bot = None):
        super().__init__(timeout=None)
        self.bot_ref = bot_ref

    @discord.ui.button(label="➕ 部署追加", style=discord.ButtonStyle.primary, custom_id="admin_add_dept_btn")
    async def add_dept(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AddDeptModal(interaction.message, interaction.client))

    @discord.ui.button(label="🗑️ 部署削除", style=discord.ButtonStyle.danger, custom_id="admin_del_dept_btn")
    async def del_dept(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not quiz_config.get("departments"):
            await interaction.response.send_message("⚠️ 削除できる部署がありません。", ephemeral=True)
            return
        await interaction.response.send_message("削除する部署を選んでください:", view=SelectDeptView("delete", interaction.message, interaction.client), ephemeral=True)

    @discord.ui.button(label="❓ 質問追加", style=discord.ButtonStyle.secondary, custom_id="admin_add_question_btn")
    async def add_question(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not quiz_config.get("departments"):
            await interaction.response.send_message("⚠️ 先に「部署追加」を行ってください。", ephemeral=True)
            return
        await interaction.response.send_message("質問を追加する部署を選んでください:", view=SelectDeptView("add_question", interaction.message, interaction.client), ephemeral=True)

    @discord.ui.button(label="🔄 募集ON/OFF機能", style=discord.ButtonStyle.secondary, custom_id="admin_toggle_status_btn")
    async def toggle_status(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not quiz_config.get("departments"):
            await interaction.response.send_message("⚠️ 設定する部署がありません。", ephemeral=True)
            return
        await interaction.response.send_message("ON/OFFを切り替える部署を選んでください:", view=SelectDeptView("toggle", interaction.message, interaction.client), ephemeral=True)

    @discord.ui.button(label="📌 パネル送信", style=discord.ButtonStyle.success, custom_id="admin_send_panel_btn")
    async def send_panel(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="✨ 自己推薦・応募受付",
            description="下のメニューから応募したい部署を選択してください。",
            color=discord.Color.green()
        )
        await interaction.channel.send(embed=embed, view=QuizUserPanelView())
        await interaction.response.send_message("✅ このチャンネルに応募用パネルを送信しました！", ephemeral=True)

def setup_quiz_commands(bot: commands.Bot):
    bot.add_view(AdminPanelEditView(bot))
    bot.add_view(QuizUserPanelView())
    bot.add_view(ReadyCheckView(None, "", []))

    @bot.command(name="recommendadminpanel")
    @commands.has_permissions(administrator=True)
    async def recommend_admin_panel(ctx: commands.Context):
        embed = generate_admin_embed()
        view = AdminPanelEditView(bot)
        await ctx.send(embed=embed, view=view)

    @bot.command(name="testsave")
    @commands.has_permissions(administrator=True)
    async def test_save_cmd(ctx: commands.Context):
        """データ保存のテストを行う管理者用コマンド"""
        await ctx.send("💾 テスト保存を実行します...")
        await save_config_to_discord(ctx.bot)
        await ctx.send("✅ テスト保存処理が完了しました。")
