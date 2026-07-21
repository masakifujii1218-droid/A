import json
import os
import random
import time
from collections import defaultdict
import discord
from discord import app_commands

# --- 設定値 ---
DATA_FILE = "quiz_data.json"
EXEMPT_ROLE_ID = 1510405214811852900  # 制限免除ロールID
LIMIT_PER_HOUR = 15                  # 1時間あたりの回数制限
HOURLY_SECONDS = 3600                # 1時間（秒）

# 難易度の設定（表示名、倍率）
DIFFICULTY_CONFIG = {
    "easy": {"label": "🟢 初級（+20%）", "rate": 0.20, "name": "初級"},
    "normal": {"label": "🟡 中級（+30%）", "rate": 0.30, "name": "中級"},
    "hard": {"label": "🔴 上級（+50%）", "rate": 0.50, "name": "上級"},
}

# ユーザーごとの実行履歴: { user_id: [timestamp1, timestamp2, ...] }
user_quiz_history = defaultdict(list)


# --- データロード関数 ---
def load_quiz_data():
    """quiz_data.json を安全に読み込む"""
    if not os.path.exists(DATA_FILE):
        return []
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[Quiz Error] データファイルの読み込みに失敗しました: {e}")
        return []


# --- モーダル: 賭けポイント入力 ---
class BetPointModal(discord.ui.Modal, title="賭けポイントの設定"):
    bet_input = discord.ui.TextInput(
        label="賭けるポイント数を入力してください",
        placeholder="例: 100 （半角数字）",
        required=True,
        min_length=1,
        max_length=10
    )

    def __init__(self, difficulty: str, quiz_data: dict, points_funcs: tuple):
        super().__init__()
        self.difficulty = difficulty
        self.quiz_data = quiz_data
        self.get_user_points, self.update_points, self.sync_user_points, self.log_channel_id = points_funcs

    async def on_submit(self, interaction: discord.Interaction):
        # 1. 入力値の数字チェック
        if not self.bet_input.value.isdigit():
            await interaction.response.send_message("❌ 半角数字でポイントを入力してください。", ephemeral=True)
            return

        bet_amount = int(self.bet_input.value)
        if bet_amount <= 0:
            await interaction.response.send_message("❌ ポイントは1以上を指定してください。", ephemeral=True)
            return

        # 2. 所持ポイントチェック
        user_points = self.get_user_points(interaction.user.id)
        if user_points < bet_amount:
            await interaction.response.send_message(
                f"❌ ポイントが不足しています！\n現在の所持ポイント: **{user_points:,} pt**",
                ephemeral=True
            )
            return

        # 3. 安全に賭けポイントを引き落とし（二重引き落とし防止）
        old_pts, current_pts = self.update_points(interaction.user.id, -bet_amount)

        # ログ同期
        log_channel = interaction.client.get_channel(self.log_channel_id)
        if log_channel:
            await self.sync_user_points(log_channel, interaction.user.id, current_pts)

        # 4. クイズ回答用UIの作成と出題
        view = QuizQuestionView(
            quiz_data=self.quiz_data,
            difficulty=self.difficulty,
            bet_amount=bet_amount,
            user_id=interaction.user.id,
            points_funcs=(self.get_user_points, self.update_points, self.sync_user_points, self.log_channel_id)
        )

        diff_info = DIFFICULTY_CONFIG[self.difficulty]
        win_points = int(bet_amount * (1 + diff_info["rate"]))

        embed = discord.Embed(
            title=f"🧠 鉄道クイズ【{diff_info['name']}】",
            description=(
                f"**【問題】**\n{self.quiz_data['question']}\n\n"
                f"💰 **賭けポイント:** {bet_amount:,} pt\n"
                f"🎁 **正解時の獲得:** {win_points:,} pt（+{int(diff_info['rate']*100)}%）\n"
                f"💀 **不正解時:** 賭けポイント没収\n\n"
                f"⏱️ 制限時間: **60秒**"
            ),
            color=discord.Color.blue()
        )

        # 元のメッセージをクイズ画面に更新
        await interaction.response.edit_message(content=None, embed=embed, view=view)


# --- クイズ回答用 View ---
class QuizQuestionView(discord.ui.View):
    def __init__(self, quiz_data: dict, difficulty: str, bet_amount: int, user_id: int, points_funcs: tuple):
        super().__init__(timeout=60)
        self.quiz_data = quiz_data
        self.difficulty = difficulty
        self.bet_amount = bet_amount
        self.user_id = user_id
        self.get_user_points, self.update_points, self.sync_user_points, self.log_channel_id = points_funcs

        # 選択肢をシャッフルしてボタン設置
        choices = quiz_data["choices"].copy()
        random.shuffle(choices)

        for choice in choices:
            button = discord.ui.Button(label=choice, style=discord.ButtonStyle.secondary)
            button.callback = self.make_callback(choice)
            self.add_item(button)

    def make_callback(self, chosen: str):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.user_id:
                await interaction.response.send_message("❌ あなた向けのクイズではありません。", ephemeral=True)
                return

            # 連打・重複回答防止のため全ボタン無効化
            for item in self.children:
                item.disabled = True

            diff_info = DIFFICULTY_CONFIG[self.difficulty]
            is_correct = (chosen == self.quiz_data["answer"])

            if is_correct:
                # 正解時：賭け金 + 配当分を付与
                reward = int(self.bet_amount * (1 + diff_info["rate"]))
                old_pts, new_pts = self.update_points(interaction.user.id, reward)

                embed = discord.Embed(
                    title="⭕️ 正解！",
                    description=(
                        f"正解は **{self.quiz_data['answer']}** でした！\n\n"
                        f"🎉 **{reward:,} pt** を獲得しました！（元手 {self.bet_amount:,} pt + 配当）"
                    ),
                    color=discord.Color.green()
                )
            else:
                # 不正解時：すでに引き落とし済みのため処理なし
                new_pts = self.get_user_points(interaction.user.id)
                embed = discord.Embed(
                    title="❌ 不正解...",
                    description=(
                        f"残念！正解は **{self.quiz_data['answer']}** でした。\n\n"
                        f"💸 賭けた **{self.bet_amount:,} pt** は没収されました。"
                    ),
                    color=discord.Color.red()
                )

            embed.set_footer(text=f"現在の所持ポイント: {new_pts:,} pt")

            # ログチャンネル同期
            log_channel = interaction.client.get_channel(self.log_channel_id)
            if log_channel:
                await self.sync_user_points(log_channel, interaction.user.id, new_pts)

            await interaction.response.edit_message(embed=embed, view=self)
            self.stop()

        return callback

    async def on_timeout(self):
        # タイムアウト時は全ボタン無効化（賭け金は没収扱い）
        for item in self.children:
            item.disabled = True


# --- ステップ2: モーダル起動ボタン View ---
class BetStartView(discord.ui.View):
    def __init__(self, difficulty: str, quiz_data: dict, user_id: int, points_funcs: tuple):
        super().__init__(timeout=120)
        self.difficulty = difficulty
        self.quiz_data = quiz_data
        self.user_id = user_id
        self.points_funcs = points_funcs

    @discord.ui.button(label="ポイントを入力して挑戦する 💰", style=discord.ButtonStyle.success)
    async def open_modal(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ あなた向けの操作ではありません。", ephemeral=True)
            return

        modal = BetPointModal(self.difficulty, self.quiz_data, self.points_funcs)
        await interaction.response.send_modal(modal)


# --- ステップ1: 難易度選択セレクトメニュー View ---
class DifficultySelectView(discord.ui.View):
    def __init__(self, user_id: int, points_funcs: tuple):
        super().__init__(timeout=120)
        self.user_id = user_id
        self.points_funcs = points_funcs

    @discord.ui.select(
        placeholder="難易度を選択してください...",
        options=[
            discord.SelectOption(label="🟢 初級", value="easy", description="正解で +20% の配当"),
            discord.SelectOption(label="🟡 中級", value="normal", description="正解で +30% の配当"),
            discord.SelectOption(label="🔴 上級", value="hard", description="正解で +50% の配当"),
        ]
    )
    async def select_difficulty(self, interaction: discord.Interaction, select: discord.ui.Select):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ あなた向けの操作ではありません。", ephemeral=True)
            return

        selected_diff = select.values[0]
        diff_info = DIFFICULTY_CONFIG[selected_diff]

        # 全問題から該当難易度の問題を抽出
        all_quizzes = load_quiz_data()
        filtered = [q for q in all_quizzes if q.get("difficulty") == selected_diff]

        if not filtered:
            await interaction.response.send_message("❌ 該当する難易度の問題が見つかりませんでした。", ephemeral=True)
            return

        chosen_quiz = random.choice(filtered)
        get_user_points = self.points_funcs[0]
        current_pts = get_user_points(interaction.user.id)

        embed = discord.Embed(
            title="💰 賭けポイントの設定",
            description=(
                f"選択された難易度: **{diff_info['label']}**\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"**【配当ルール】**\n"
                f"🟢 **初級** ➔ 正解: **+20%**\n"
                f"🟡 **中級** ➔ 正解: **+30%**\n"
                f"🔴 **上級** ➔ 正解: **+50%**\n"
                f"❌ **不正解** ➔ **全額没収**\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"現在の所持ポイント: **{current_pts:,} pt**\n"
                f"下のボタンを押して賭けポイントを入力してください！"
            ),
            color=discord.Color.gold()
        )

        view = BetStartView(selected_diff, chosen_quiz, self.user_id, self.points_funcs)
        await interaction.response.edit_message(embed=embed, view=view)


# --- 外部結合用セットアップ関数 ---
def setup_quiz(bot, get_user_points_func, update_points_func, sync_points_func, log_channel_id: int):
    """sub.py などのメイン処理から呼び出す登録用関数"""
    points_funcs = (get_user_points_func, update_points_func, sync_points_func, log_channel_id)

    @bot.tree.command(name="quiz", description="鉄道クイズに挑戦してポイントを増やそう！")
    async def quiz_command(interaction: discord.Interaction):
        user = interaction.user
        now = time.time()

        # 免除ロールを持っているか判定
        has_exempt_role = any(role.id == EXEMPT_ROLE_ID for role in user.roles)

        if not has_exempt_role:
            # 1時間以内の実行履歴をフィルタリング
            user_quiz_history[user.id] = [t for t in user_quiz_history[user.id] if now - t < HOURLY_SECONDS]

            if len(user_quiz_history[user.id]) >= LIMIT_PER_HOUR:
                oldest_time = user_quiz_history[user.id][0]
                remaining_sec = int(HOURLY_SECONDS - (now - oldest_time))
                minutes, seconds = divmod(remaining_sec, 60)

                await interaction.response.send_message(
                    f"⏳ 1時間の制限（15回まで）に達しました！\nあと **{minutes}分{seconds}秒** お待ちください。",
                    ephemeral=True
                )
                return

            # 回数制限カウント追加
            user_quiz_history[user.id].append(now)

        # 所持ポイントチェック（最低1pt必要）
        current_pts = get_user_points_func(user.id)
        if current_pts <= 0:
            await interaction.response.send_message("❌ クイズに挑戦するためのポイントが足りません！", ephemeral=True)
            return

        embed = discord.Embed(
            title="🧠 鉄道クイズ挑戦",
            description="下のメニューから挑戦したい**難易度**を選択してください！",
            color=discord.Color.blue()
        )

        view = DifficultySelectView(user.id, points_funcs)
        await interaction.response.send_message(embed=embed, view=view)
