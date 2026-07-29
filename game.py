import discord
from discord import app_commands
from discord.ext import commands
import random
import asyncio

# ==========================================
# 1. 💣 爆弾解除ゲーム UI
# ==========================================
class BombView(discord.ui.View):
    def __init__(self, author: discord.User):
        super().__init__(timeout=60)
        self.author = author
        # 4本のうち1本が爆弾
        self.bomb_index = random.randint(0, 3)
        self.safe_count = 0

        wires = [
            ("🔴 赤いワイヤー", discord.ButtonStyle.danger, 0),
            ("🔵 青いワイヤー", discord.ButtonStyle.primary, 1),
            ("🟢 緑のワイヤー", discord.ButtonStyle.success, 2),
            ("🟡 黄色のワイヤー", discord.ButtonStyle.secondary, 3),
        ]

        for label, style, idx in wires:
            button = discord.ui.Button(label=label, style=style, custom_id=str(idx))
            button.callback = self.make_callback(idx)
            self.add_item(button)

    def make_callback(self, idx: int):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.author.id:
                await interaction.response.send_message("⚠️ あなた専用のゲームではありません！", ephemeral=True)
                return

            # 押されたボタンを無効化
            for child in self.children:
                if isinstance(child, discord.ui.Button) and child.custom_id == str(idx):
                    child.disabled = True
                    break

            if idx == self.bomb_index:
                # 爆発！
                embed = discord.Embed(
                    title="💥 ドカーン！ 爆発しました！",
                    description="セーフティワイヤーを切断できませんでした... ゲームオーバー！ 💀",
                    color=discord.Color.red()
                )
                for child in self.children:
                    child.disabled = True
                await interaction.response.edit_message(embed=embed, view=self)
            else:
                self.safe_count += 1
                if self.safe_count == 3:
                    # 爆弾以外の3本をすべて切断成功
                    embed = discord.Embed(
                        title="🎉 爆弾解除成功！",
                        description="見事にすべてのセーフティワイヤーを解除しました！お見事！ ✨",
                        color=discord.Color.green()
                    )
                    for child in self.children:
                        child.disabled = True
                    await interaction.response.edit_message(embed=embed, view=self)
                else:
                    embed = discord.Embed(
                        title="✂️ ワイヤー切断完了...",
                        description=f"セーフ！爆発しませんでした！\n残りワイヤー: **{3 - self.safe_count}本**",
                        color=discord.Color.gold()
                    )
                    await interaction.response.edit_message(embed=embed, view=self)

        return callback


# ==========================================
# 2. ❌⭕️ ○×ゲーム UI
# ==========================================
class TicTacToeButton(discord.ui.Button):
    def __init__(self, x: int, y: int):
        super().__init__(style=discord.ButtonStyle.secondary, label="\u200b", row=y)
        self.x = x
        self.y = y

    async def callback(self, interaction: discord.Interaction):
        assert self.view is not None
        view: TicTacToeView = self.view

        # 手番チェック
        if interaction.user.id != view.current_player.id:
            await interaction.response.send_message("⚠️ あなたのターンではありません！", ephemeral=True)
            return

        if view.board[self.y][self.x] != 0:
            await interaction.response.send_message("⚠️ そこには既にマークが配置されています！", ephemeral=True)
            return

        # マーク配置
        if view.current_player == view.player_x:
            self.style = discord.ButtonStyle.danger
            self.label = "❌"
            view.board[self.y][self.x] = 1
            next_player = view.player_o
        else:
            self.style = discord.ButtonStyle.primary
            self.label = "⭕️"
            view.board[self.y][self.x] = 2
            next_player = view.player_x

        self.disabled = True
        winner = view.check_winner()

        if winner is not None:
            if winner == 1:
                content = f"🎉 **{view.player_x.mention} (❌) の勝ち！**"
            elif winner == 2:
                content = f"🎉 **{view.player_o.mention} (⭕️) の勝ち！**"
            else:
                content = "🤝 **引き分けです！**"

            for child in view.children:
                child.disabled = True
            await interaction.response.edit_message(content=content, view=view)
        else:
            view.current_player = next_player
            await interaction.response.edit_message(
                content=f"❌⭕️ **○×ゲーム**\n現在の手番: {view.current_player.mention}",
                view=view
            )


class TicTacToeView(discord.ui.View):
    def __init__(self, player_x: discord.User, player_o: discord.User):
        super().__init__(timeout=120)
        self.player_x = player_x
        self.player_o = player_o
        self.current_player = player_x
        # 0: 空き, 1: X, 2: O
        self.board = [[0, 0, 0], [0, 0, 0], [0, 0, 0]]

        for y in range(3):
            for x in range(3):
                self.add_item(TicTacToeButton(x, y))

    def check_winner(self):
        # 横・縦チェック
        for i in range(3):
            if self.board[i][0] == self.board[i][1] == self.board[i][2] != 0:
                return self.board[i][0]
            if self.board[0][i] == self.board[1][i] == self.board[2][i] != 0:
                return self.board[0][i]

        # 斜めチェック
        if self.board[0][0] == self.board[1][1] == self.board[2][2] != 0:
            return self.board[0][0]
        if self.board[0][2] == self.board[1][1] == self.board[2][0] != 0:
            return self.board[0][2]

        # 盤面が埋まっているかチェック（引き分け）
        if all(cell != 0 for row in self.board for cell in row):
            return 0

        return None


# ==========================================
# 3. 🎴 ハイ＆ロー UI
# ==========================================
class HighLowView(discord.ui.View):
    def __init__(self, author: discord.User, current_card: int, streak: int = 0):
        super().__init__(timeout=60)
        self.author = author
        self.current_card = current_card
        self.streak = streak

    async def _handle_choice(self, interaction: discord.Interaction, choice: str):
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("⚠️ あなた専用のゲームではありません！", ephemeral=True)
            return

        next_card = random.randint(1, 13)

        if next_card == self.current_card:
            embed = discord.Embed(
                title="🎴 ハイ＆ロー (引き分け！)",
                description=f"カードは同じ数字 **【{next_card}】** でした！\n現在の連勝数: **{self.streak}勝**\n\n次のカードは **【{next_card}】** より High か Low か？",
                color=discord.Color.gold()
            )
            view = HighLowView(self.author, next_card, self.streak)
            await interaction.response.edit_message(embed=embed, view=view)
            return

        is_high = next_card > self.current_card
        is_correct = (choice == "HIGH" and is_high) or (choice == "LOW" and not is_high)

        if is_correct:
            new_streak = self.streak + 1
            embed = discord.Embed(
                title="🎉 正解！ゲーム継続！",
                description=f"前のカード: **【{self.current_card}】** ➔ 次のカード: **【{next_card}】**\n見事当たりました！現在 **{new_streak}連勝中**！\n\n次のカードは **【{next_card}】** より High か Low か？",
                color=discord.Color.green()
            )
            view = HighLowView(self.author, next_card, new_streak)
            await interaction.response.edit_message(embed=embed, view=view)
        else:
            embed = discord.Embed(
                title="💀 ゲームオーバー！",
                description=f"前のカード: **【{self.current_card}】** ➔ 次のカード: **【{next_card}】**\n残念！ハズレです。\n\n**最終記録: {self.streak}連勝**",
                color=discord.Color.red()
            )
            for child in self.children:
                child.disabled = True
            await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="🔴 High (高い)", style=discord.ButtonStyle.danger)
    async def high_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle_choice(interaction, "HIGH")

    @discord.ui.button(label="🔵 Low (低い)", style=discord.ButtonStyle.primary)
    async def low_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle_choice(interaction, "LOW")


# ==========================================
# 4. ✊✌️✋ じゃんけん UI
# ==========================================
class JankenView(discord.ui.View):
    def __init__(self, author: discord.User):
        super().__init__(timeout=60)
        self.author = author

    async def _handle_janken(self, interaction: discord.Interaction, user_choice: str):
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("⚠️ あなた専用のゲームではありません！", ephemeral=True)
            return

        bot_choice = random.choice(["グー ✊", "チョキ ✌️", "パー ✋"])
        win_map = {"グー ✊": "チョキ ✌️", "チョキ ✌️": "パー ✋", "パー ✋": "グー ✊"}

        if user_choice == bot_choice:
            result = "引き分け！ 🤝"
            color = discord.Color.gold()
        elif win_map[user_choice] == bot_choice:
            result = "あなたの勝ち！ 🎉"
            color = discord.Color.green()
        else:
            result = "あなたの負け... 💀"
            color = discord.Color.red()

        embed = discord.Embed(title="✊✌️✋ じゃんけん結果", color=color)
        embed.add_field(name="あなた", value=user_choice, inline=True)
        embed.add_field(name="Bot", value=bot_choice, inline=True)
        embed.add_field(name="結果", value=f"**{result}**", inline=False)

        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="グー ✊", style=discord.ButtonStyle.primary)
    async def rock(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle_janken(interaction, "グー ✊")

    @discord.ui.button(label="チョキ ✌️", style=discord.ButtonStyle.success)
    async def scissors(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle_janken(interaction, "チョキ ✌️")

    @discord.ui.button(label="パー ✋", style=discord.ButtonStyle.danger)
    async def paper(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle_janken(interaction, "パー ✋")


# ==========================================
# 5. GameCog 本体 (コマンド定義)
# ==========================================
class GameCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # 💣 爆弾解除 (/bomb)
    @app_commands.command(name="bomb", description="爆発しない安全なワイヤーを切断して爆弾を解除しよう！")
    async def bomb(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="💣 爆弾解除ミッション",
            description="4本のワイヤーのうち **1本だけが爆破用スイッチ** です！\n安全なワイヤーを慎重に選んで切断してください。",
            color=discord.Color.dark_theme()
        )
        view = BombView(interaction.user)
        await interaction.response.send_message(embed=embed, view=view)

    # ❌⭕️ ○×ゲーム (/tictactoe)
    @app_commands.command(name="tictactoe", description="相手を指定して○×ゲーム（三目並べ）で対戦！")
    @app_commands.describe(opponent="対戦相手のユーザーを選択してください")
    async def tictactoe(self, interaction: discord.Interaction, opponent: discord.User):
        if opponent.bot:
            await interaction.response.send_message("⚠️ Botと対戦することはできません。", ephemeral=True)
            return
        if opponent.id == interaction.user.id:
            await interaction.response.send_message("⚠️ 自分自身と対戦することはできません。", ephemeral=True)
            return

        view = TicTacToeView(player_x=interaction.user, player_o=opponent)
        await interaction.response.send_message(
            content=f"❌⭕️ **○×ゲーム**\n先手 (❌): {interaction.user.mention}\n後手 (⭕️): {opponent.mention}\n\n現在の手番: {interaction.user.mention}",
            view=view
        )

    # 🎴 ハイ＆ロー (/highlow)
    @app_commands.command(name="highlow", description="次のカードが今より大きい(High)か小さい(Low)か当てる連続チャレンジ！")
    async def highlow(self, interaction: discord.Interaction):
        first_card = random.randint(1, 13)
        embed = discord.Embed(
            title="🎴 ハイ＆ロー スタート！",
            description=f"現在のカードは **【{first_card}】** です。\n次のカード(1〜13)はこの数字より **High** か **Low** か選択してください！",
            color=discord.Color.blurple()
        )
        view = HighLowView(interaction.user, first_card, streak=0)
        await interaction.response.send_message(embed=embed, view=view)

    # 🎰 おみくじ (/omikuji)
    @app_commands.command(name="omikuji", description="今日の運勢を占います！")
    async def omikuji(self, interaction: discord.Interaction):
        results = [
            ("大吉 🌟", "最高の1日になりそう！", discord.Color.gold()),
            ("中吉 😊", "良いことがありそう！", discord.Color.green()),
            ("小吉 🙂", "穏やかな1日になりそう。", discord.Color.blue()),
            ("吉 🌿", "普通が一番！", discord.Color.teal()),
            ("末吉 😅", "慎重に行動しよう。", discord.Color.orange()),
            ("凶 ⚠️", "油断は禁物！", discord.Color.red()),
        ]
        res, desc, color = random.choice(results)
        embed = discord.Embed(title=f"🎰 {interaction.user.display_name} さんの運勢", description=f"**【{res}】**\n{desc}", color=color)
        await interaction.response.send_message(embed=embed)

    # ✊✌️✋ じゃんけん (/janken)
    @app_commands.command(name="janken", description="Botとじゃんけん勝負！")
    async def janken(self, interaction: discord.Interaction):
        embed = discord.Embed(title="✊✌️✋ じゃんけん", description="手を選んでボタンを押してください！", color=discord.Color.blurple())
        view = JankenView(interaction.user)
        await interaction.response.send_message(embed=embed, view=view)

    # 🎮 数当てゲーム (/numguess)
    @app_commands.command(name="numguess", description="1〜100の数字を当てるミニゲーム")
    async def numguess(self, interaction: discord.Interaction):
        target = random.randint(1, 130)
        await interaction.response.send_message("🎮 **数当てゲーム開始！**\n1〜100の中から数字を1つ決めました。\nチャットに数字を送信して当ててください！（制限時間: 60秒 / 最大7回）")

        def check(m: discord.Message):
            return m.author.id == interaction.user.id and m.channel.id == interaction.channel.id and m.content.isdigit()

        attempts = 0
        while attempts < 7:
            try:
                msg = await self.bot.wait_for("message", check=check, timeout=60.0)
                guess = int(msg.content)
                attempts += 1

                if guess == target:
                    await msg.reply(f"🎯 **正解！** {attempts}回目で当たりました！お見事！")
                    return
                elif guess < target:
                    await msg.reply(f"📈 **もっと大きい**数字です！（試行: {attempts}/7回）")
                else:
                    await msg.reply(f"📉 **もっと小さい**数字です！（試行: {attempts}/7回）")
            except asyncio.TimeoutError:
                await interaction.followup.send(f"⏱️ タイムアウト！正解は **{target}** でした。")
                return

        await interaction.followup.send(f"💀 残念！正解は **{target}** でした。")

    # 🎯 選択 (`/choice`)
    @app_commands.command(name="choice", description="指定した選択肢の中から1つをランダムで選びます")
    @app_commands.describe(options="カンマ(,)区切りで選択肢を入力 (例: ラーメン, パスタ, カレー)")
    async def choice(self, interaction: discord.Interaction, options: str):
        choices = [opt.strip() for opt in options.split(",") if opt.strip()]
        if len(choices) < 2:
            await interaction.response.send_message("⚠️ カンマ(,)で区切って2つ以上の選択肢を入力してください。", ephemeral=True)
            return
        selected = random.choice(choices)
        await interaction.response.send_message(f"🎯 選ばれたのは **【{selected}】** です！")


async def setup(bot: commands.Bot):
    await bot.add_cog(GameCog(bot))
