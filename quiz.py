import io
import json
import os
import discord
from discord import app_commands
from discord.ext import commands

# --- 各種ID設定 ---
DEFAULT_CATEGORY_ID = 1513901626610553043  # チケット作成先カテゴリーID
LOG_CHANNEL_ID = 1510042822533840936       # 面接回答ログ送信先チャンネルID
DATA_CHANNEL_ID = 1526289865719943329      # 設定データ保存・復旧用チャンネルID

# 基準となるロールID（上層部ロールID）
BASE_ADMIN_ROLE_ID = 1510405214811852900

CONFIG_DATA = {"departments": {}}


# ユーザーが「上層部」以上のロールまたは管理者権限を持っているか判定
def is_admin(user: discord.Member) -> bool:
    # Discordの「管理者(Administrator)」権限があれば無条件で許可
    if user.guild_permissions.administrator:
        return True

    # サーバー内の「上層部」ロールを取得
    base_role = user.guild.get_role(BASE_ADMIN_ROLE_ID)
    if not base_role:
        # 万が一基準ロールが見つからない場合はロール所持チェックでフォールバック
        return any(role.id == BASE_ADMIN_ROLE_ID for role in user.roles)

    # ユーザーが持っているロールの中に、上層部と同等かそれ以上の階層(position)のものがあるか確認
    return any(role.position >= base_role.position for role in user.roles)


# --- クラウド保存・復旧処理 (Discordチャンネル経由) ---
async def load_config_from_discord(bot):
    global CONFIG_DATA
    channel = bot.get_channel(DATA_CHANNEL_ID)
    if not channel:
        print(f"⚠️ データ保存用チャンネル (ID: {DATA_CHANNEL_ID}) が見つかりません。")
        return

    async for msg in channel.history(limit=10):
        if msg.attachments and msg.attachments[0].filename == "recommend_config.json":
            content = await msg.attachments[0].read()
            CONFIG_DATA = json.loads(content.decode("utf-8"))
            print("✅ Discord保存用チャンネルから最新データを自動復旧しました！")
            return
    print("ℹ️ データが見つからなかったため初期化します。")


async def save_config_to_discord(bot):
    global CONFIG_DATA
    channel = bot.get_channel(DATA_CHANNEL_ID)
    if not channel:
        print(f"❌ データ保存用チャンネル (ID: {DATA_CHANNEL_ID}) が見つかりません。")
        return

    json_data = json.dumps(CONFIG_DATA, ensure_ascii=False, indent=2)
    file = discord.File(
        io.BytesIO(json_data.encode("utf-8")), filename="recommend_config.json"
    )
    await channel.send("📂 **【システムデータ自動バックアップ】**", file=file)


# --- ユーザー情報Embed生成 ---
def create_user_info_embed(member: discord.Member):
    roles = [role.mention for role in member.roles if role != member.guild.default_role]
    roles_str = ", ".join(roles) if roles else "なし"
    joined_at = member.joined_at.strftime("%Y/%m/%d %H:%M") if member.joined_at else "不明"

    embed = discord.Embed(title="📩 新規問い合わせチケット", color=discord.Color.blue())
    embed.add_field(name="👤 ユーザー名", value=f"{member.mention} ({member.name})", inline=False)
    embed.add_field(name="🆔 ユーザーID", value=f"`{member.id}`", inline=False)
    embed.add_field(name="📅 サーバー参加日", value=joined_at, inline=False)
    embed.add_field(name="🛡️ 所持ロール", value=roles_str, inline=False)
    return embed


# --- クローズボタン付きビュー ---
class TicketControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔒 チケットを閉じる", style=discord.ButtonStyle.danger, custom_id="close_ticket_btn")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_admin(interaction.user):
            await interaction.response.send_message("❌ チケットを閉じる権限がありません（上層部以上専用）。", ephemeral=True)
            return

        await interaction.response.send_message("⚠️ このチケットを 5秒後 に削除します...")
        import asyncio
        await asyncio.sleep(5)
        await interaction.channel.delete()


# --- 面接対話処理（質問スタート） ---
async def start_interview(interaction: discord.Interaction, dept_name: str):
    questions = CONFIG_DATA["departments"].get(dept_name, {}).get("questions", [])

    if not questions:
        await interaction.channel.send("⚠️ この部署にはまだ質問が設定されていません。管理者の対応をお待ちください。")
        return

    answers = []

    def check(m):
        return m.author == interaction.user and m.channel == interaction.channel

    for idx, q_text in enumerate(questions, start=1):
        await interaction.channel.send(f"**{idx}: {q_text}**")
        try:
            msg = await interaction.client.wait_for("message", check=check, timeout=300.0)
            answers.append((q_text, msg.content))
        except Exception:
            await interaction.channel.send("⏱️ 応答時間（5分）を超えました。面接を中断します。")
            return

    summary_embed = discord.Embed(title=f"📋 【{dept_name}】応募回答一覧", color=discord.Color.green())
    for idx, (q, a) in enumerate(answers, start=1):
        summary_embed.add_field(name=f"問{idx}: {q}", value=a, inline=False)

    await interaction.channel.send("✅ すべての質問が完了しました！回答内容は以下の通りです。", embed=summary_embed)

    log_channel = interaction.guild.get_channel(LOG_CHANNEL_ID)
    if log_channel:
        log_text = f"USERNAME: {interaction.user.mention} (`{interaction.user.name}`)\n"
        log_text += f"質問：\n"
        log_text += f"回答：\n"
        log_text += "━━━━━━━━━━━━━━━━━━━\n"
        for q, a in answers:
            log_text += f"質問：{q}\n回答：{a}\n---\n"
        await log_channel.send(log_text)


# --- 一般ユーザー用：部署選択ドロップダウン ---
class DepartmentSelect(discord.ui.Select):
    def __init__(self, open_departments):
        options = [
            discord.SelectOption(label=dept, description=f"{dept}への自己推薦")
            for dept in open_departments
        ]
        super().__init__(placeholder="応募したい部署を選択してください...", options=options)

    async def callback(self, interaction: discord.Interaction):
        dept_name = self.values[0]
        category = interaction.guild.get_channel(DEFAULT_CATEGORY_ID)

        if not category or not isinstance(category, discord.CategoryChannel):
            await interaction.response.send_message(f"❌ 指定のカテゴリー(ID: {DEFAULT_CATEGORY_ID})が見つかりません。", ephemeral=True)
            return

        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            interaction.guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }

        # 「上層部」以上の階層を持つ全ロールにチケットの閲覧・送信権限を付与
        base_role = interaction.guild.get_role(BASE_ADMIN_ROLE_ID)
        if base_role:
            for role in interaction.guild.roles:
                if role.position >= base_role.position:
                    overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

        channel_name = f"求職-{interaction.user.name}"
        ticket_channel = await category.create_text_channel(name=channel_name, overwrites=overwrites)

        await interaction.response.send_message(f"✅ 面接チケットを作成しました: {ticket_channel.mention}", ephemeral=True)

        user_embed = create_user_info_embed(interaction.user)
        await ticket_channel.send(embed=user_embed, view=TicketControlView())
        await start_interview(interaction, dept_name)


class DepartmentSelectView(discord.ui.View):
    def __init__(self, open_departments):
        super().__init__(timeout=None)
        self.add_item(DepartmentSelect(open_departments))


# --- 一般ユーザー用パネルのボタン ---
class UserPanelButton(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="応募する", style=discord.ButtonStyle.primary, custom_id="recommend_apply_btn")
    async def apply(self, interaction: discord.Interaction, button: discord.ui.Button):
        departments = CONFIG_DATA.get("departments", {})
        open_departments = [dept for dept, info in departments.items() if info.get("is_open", True)]

        if not open_departments:
            await interaction.response.send_message("🚫 現在、募集中の部署はありません。", ephemeral=True)
            return

        await interaction.response.send_message(
            "希望する部署を選択してください：",
            view=DepartmentSelectView(open_departments),
            ephemeral=True
        )


# --- モーダル（文字入力フォーム） ---
class AddDepartmentModal(discord.ui.Modal, title="部署の追加"):
    dept_name = discord.ui.TextInput(label="部署名", placeholder="例: 開発部、広報部など")

    async def on_submit(self, interaction: discord.Interaction):
        if self.dept_name.value in CONFIG_DATA["departments"]:
            await interaction.response.send_message("⚠️ その部署は既に登録されています。", ephemeral=True)
            return

        CONFIG_DATA["departments"][self.dept_name.value] = {"is_open": True, "questions": []}
        await save_config_to_discord(interaction.client)
        await interaction.response.send_message(f"✅ 部署『{self.dept_name.value}』を追加し、保存しました！", ephemeral=True)


class AddQuestionModal(discord.ui.Modal, title="質問の一括追加"):
    def __init__(self, dept_name):
        super().__init__()
        self.dept_name = dept_name
        self.q_text = discord.ui.TextInput(
            label=f"【{dept_name}】への質問内容 (改行で複数追加)",
            style=discord.TextStyle.paragraph,
            placeholder="改行して入力すると複数の質問を一括登録できます\n例:\n志望動機を教えてください\n過去の実績はありますか？",
            max_length=2000
        )
        self.add_item(self.q_text)

    async def on_submit(self, interaction: discord.Interaction):
        if self.dept_name in CONFIG_DATA["departments"]:
            new_questions = [q.strip() for q in self.q_text.value.split("\n") if q.strip()]

            if not new_questions:
                await interaction.response.send_message("⚠️ 質問テキストが入力されていません。", ephemeral=True)
                return

            CONFIG_DATA["departments"][self.dept_name]["questions"].extend(new_questions)
            await save_config_to_discord(interaction.client)

            count = len(new_questions)
            await interaction.response.send_message(f"✅ 『{self.dept_name}』に {count} 件の質問を追加・保存しました！", ephemeral=True)


# --- 管理者パネルUI ---
class AdminPanelEditView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="➕ 部署追加", style=discord.ButtonStyle.success)
    async def add_dept(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AddDepartmentModal())

    @discord.ui.button(label="🗑️ 部署削除", style=discord.ButtonStyle.danger)
    async def delete_dept(self, interaction: discord.Interaction, button: discord.ui.Button):
        depts = CONFIG_DATA.get("departments", {})
        if not depts:
            await interaction.response.send_message("❌ 削除できる部署がありません。", ephemeral=True)
            return

        select = discord.ui.Select(placeholder="削除する部署を選択してください...")
        for d in depts.keys():
            select.add_option(label=d)

        async def select_callback(inter: discord.Interaction):
            target = select.values[0]
            del CONFIG_DATA["departments"][target]
            await save_config_to_discord(inter.client)
            await inter.response.send_message(f"🗑️ 部署『{target}』を削除しました！", ephemeral=True)

        select.callback = select_callback
        view = discord.ui.View()
        view.add_item(select)
        await interaction.response.send_message("削除したい部署を選んでください：", view=view, ephemeral=True)

    @discord.ui.button(label="❓ 質問追加", style=discord.ButtonStyle.primary)
    async def add_q(self, interaction: discord.Interaction, button: discord.ui.Button):
        depts = CONFIG_DATA.get("departments", {})
        if not depts:
            await interaction.response.send_message("❌ まず部署を追加してください。", ephemeral=True)
            return

        select = discord.ui.Select(placeholder="質問を追加したい部署を選択...")
        for d in depts.keys():
            select.add_option(label=d)

        async def select_callback(inter: discord.Interaction):
            await inter.response.send_modal(AddQuestionModal(select.values[0]))

        select.callback = select_callback
        view = discord.ui.View()
        view.add_item(select)
        await interaction.response.send_message("部署を選んでください：", view=view, ephemeral=True)

    @discord.ui.button(label="🔄 募集ON/OFF切替", style=discord.ButtonStyle.warning)
    async def toggle_dept_open(self, interaction: discord.Interaction, button: discord.ui.Button):
        depts = CONFIG_DATA.get("departments", {})
        if not depts:
            await interaction.response.send_message("❌ 部署が登録されていません。", ephemeral=True)
            return

        select = discord.ui.Select(placeholder="募集状態を切り替える部署を選択...")
        for d, info in depts.items():
            status_str = "🟢募集ON" if info.get("is_open", True) else "🔴募集OFF"
            select.add_option(label=d, description=f"現在: {status_str}")

        async def select_callback(inter: discord.Interaction):
            target_dept = select.values[0]
            current_status = CONFIG_DATA["departments"][target_dept].get("is_open", True)
            CONFIG_DATA["departments"][target_dept]["is_open"] = not current_status
            await save_config_to_discord(inter.client)

            new_status = "🟢 募集受付中" if CONFIG_DATA["departments"][target_dept]["is_open"] else "🔴 募集停止中"
            await inter.response.send_message(f"✅ 『{target_dept}』の募集状態を **{new_status}** に変更・保存しました！", ephemeral=True)

        select.callback = select_callback
        view = discord.ui.View()
        view.add_item(select)
        await interaction.response.send_message("状態を変更する部署を選んでください：", view=view, ephemeral=True)

    @discord.ui.button(label="📢 パネル送信", style=discord.ButtonStyle.secondary)
    async def send_panel(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="📄 自己推薦・社員募集パネル",
            description="以下の「応募する」ボタンを押して、希望する部署の面接チケットを開設してください。",
            color=discord.Color.gold()
        )
        await interaction.channel.send(embed=embed, view=UserPanelButton())
        await interaction.response.send_message("✅ 応募パネルを設置しました！", ephemeral=True)


# --- main.py から登録するための関数 ---
def setup_quiz_commands(bot):
    @bot.command(name="recommendadminpanel")
    async def recommend_admin_panel(ctx):
        if not is_admin(ctx.author):
            await ctx.send("❌ このコマンドを使用する権限がありません（「上層部」以上のロールが必要です）。")
            return

        depts_summary = []
        for d, info in CONFIG_DATA.get("departments", {}).items():
            status = "🟢" if info.get("is_open", True) else "🔴"
            q_count = len(info.get("questions", []))
            depts_summary.append(f"・**{d}**: {status} (質問{q_count}個)")

        summary_text = "\n".join(depts_summary) if depts_summary else "（部署未登録）"

        embed = discord.Embed(
            title="⚙️ 自己推薦 システム管理者パネル",
            description=f"**【現在の部署一覧】**\n{summary_text}\n\n下のボタンから部署の追加・削除・質問設定・ON/OFF切替が行えます。",
            color=discord.Color.dark_grey()
        )
        await ctx.send(embed=embed, view=AdminPanelEditView())

    @bot.command(name="recommendpanel")
    async def recommend_panel(ctx):
        embed = discord.Embed(
            title="📄 自己推薦・社員募集パネル",
            description="下の「応募する」ボタンを押して希望する部署を選択し、質問に回答してください。",
            color=discord.Color.blue()
        )
        await ctx.send(embed=embed, view=UserPanelButton())
