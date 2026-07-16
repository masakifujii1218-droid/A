import discord
from discord import app_commands
import json
import random
import os
from datetime import datetime

# ⚠️ あなたが前回設定した「消えないフォルダ」の中のポイントデータJSONのパスに書き換えてください！
POINTS_FILE_PATH = "消えないフォルダ/points.json"  # ← ここを書き換える！
QUIZ_FILE_PATH = "quiz_data.json"

# --- 今のBotの「通帳機能」と完全に同期するデータ読み書き関数 ---
def get_user_data(user_id: str) -> dict:
    """ユーザーの全データ（ポイントと履歴）を取得する"""
    if not os.path.exists(POINTS_FILE_PATH):
        return {"points": 0, "logs": []}
    try:
        with open(POINTS_FILE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get(user_id, {"points": 0, "logs": []})
    except Exception:
        return {"points": 0, "logs": []}

def update_user_quiz_result(user_id: str, amount_change: int, log_message: str):
    """ポイントを増減させ、同時に『通帳（logs）』にも履歴を書き込んで保存する"""
    all_data = {}
    if os.path.exists(POINTS_FILE_PATH):
        try:
            with open(POINTS_FILE_PATH, "r", encoding="utf-8") as f:
                all_data = json.load(f)
        except Exception:
            all_data = {}
    
    # 既存のユーザーデータを取得、なければ新規作成
    user_data = all_data.get(user_id, {"points": 0, "logs": []})
    
    # ポイントの更新（マイナスにならないようにする）
    current_points = user_data.get("points", 0)
    new_points = max(0, current_points + amount_change)
    user_data["points"] = new_points
    
    # 履歴（ログ）の追加
    logs = user_data.get("logs", [])
    now_str = datetime.now().strftime("%Y/%m/%d %H:%M")
    new_log_entry = f"[{now_str}] {log_message}"
    logs.append(new_log_entry)
    
    # 履歴が100件を超えたら古い順に削除して、最大100件をキープ
    if len(logs) > 100:
        logs = logs[-100:]
    user_data["logs"] = logs
    
    # 全体データを保存
    all_data[user_id] = user_data
    with open(POINTS_FILE_PATH, "w", encoding="utf-8") as f:
        json.dump(all_data, f, indent=4, ensure_ascii=False)


def load_quiz_data():
    if not os.path.exists(QUIZ_FILE_PATH):
        return {}
    with open(QUIZ_FILE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def setup_quiz_command(tree: app_commands.CommandTree):
    
    @tree.command(name="quiz", description="ポイントを賭けて鉄道クイズに挑戦！みんなで結果を見届けよう！")
    @app_commands.describe(bet="賭けるポイント（100〜1000pt）")
    async def quiz(interaction: discord.Interaction, bet: int):
        user_id = str(interaction.user.id)
        
        # 1. ベット額の範囲制限
        if bet < 100 or bet > 1000:
            await interaction.response.send_message("❌ ベット額は100ptから1000ptの間で指定してください！", ephemeral=True)
            return

        # 2. 所持ポイントの確認（今のBotのデータから読み込む）
        user_data = get_user_data(user_id)
        user_points = user_data.get("points", 0)
        
        if user_points < bet:
            await interaction.response.send_message(f"❌ ポイントが足りません！\nあなたの所持ポイント: {user_points} pt", ephemeral=True)
            return

        quiz_bank = load_quiz_data()
        if not quiz_bank:
            await interaction.response.send_message("⚠️ クイズデータが見つかりません。管理者に確認してください。", ephemeral=True)
            return

        # 3. 難易度選択ボタン
        class DifficultyView(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=30.0)
                self.value = None

            @discord.ui.button(label="簡単 (+25% / 全没収)", style=discord.ButtonStyle.success)
            async def easy(self, button_interaction: discord.Interaction, button: discord.ui.Button):
                if button_interaction.user.id != interaction.user.id:
                    await button_interaction.response.send_message("これはあなた専用のクイズです！", ephemeral=True)
                    return
                self.value = "簡単"
                self.stop()
                await button_interaction.response.defer()

            @discord.ui.button(label="普通 (+50% / 全没収)", style=discord.ButtonStyle.primary)
            async def normal(self, button_interaction: discord.Interaction, button: discord.ui.Button):
                if button_interaction.user.id != interaction.user.id:
                    await button_interaction.response.send_message("これはあなた専用のクイズです！", ephemeral=True)
                    return
                self.value = "普通"
                self.stop()
                await button_interaction.response.defer()

            @discord.ui.button(label="難しい (2倍 / 10%返還)", style=discord.ButtonStyle.danger)
            async def hard(self, button_interaction: discord.Interaction, button: discord.ui.Button):
                if button_interaction.user.id != interaction.user.id:
                    await button_interaction.response.send_message("これはあなた専用のクイズです！", ephemeral=True)
                    return
                self.value = "難しい"
                self.stop()
                await button_interaction.response.defer()

        view = DifficultyView()
        await interaction.response.send_message(
            f"🎰 **{interaction.user.display_name}さん**が **{bet} pt** を賭けて鉄道クイズに挑戦します！\nまずは難易度を選択してください...（残り30秒）", 
            view=view
        )

        await view.wait()

        if view.value is None:
            await interaction.edit_original_response(content=f"⏱️ 難易度選択の時間切れにより、クイズはキャンセルされました。", view=None)
            return

        difficulty = view.value
        questions = quiz_bank.get(difficulty, [])
        if not questions:
            await interaction.edit_original_response(content="⚠️ 指定された難易度の問題が登録されていません。", view=None)
            return

        quiz_data = random.choice(questions)
        correct_ans = quiz_data["answer"]
        options = list(quiz_data["options"])
        random.shuffle(options)

        # 4. 回答用セレクトメニュー
        class QuizSelect(discord.ui.Select):
            def __init__(self):
                select_options = [discord.SelectOption(label=opt, value=opt) for opt in options]
                super().__init__(placeholder="ここをタップして答えを選択...", options=select_options)

            async def callback(self, select_interaction: discord.Interaction):
                if select_interaction.user.id != interaction.user.id:
                    await select_interaction.response.send_message("これはあなた専用のクイズです！", ephemeral=True)
                    return
                self.view.selected_answer = self.values[0]
                self.view.stop()
                await select_interaction.response.defer()

        class QuizView(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=30.0)
                self.selected_answer = None
                self.add_item(QuizSelect())

        quiz_view = QuizView()
        
        await interaction.edit_original_response(
            content=f"📊 **挑戦者: {interaction.user.display_name}さん** (賭け金: {bet} pt)\n"
                    f"**難易度: {difficulty}**\n\n"
                    f"**Q: {quiz_data['question']}**\n"
                    f"（解答制限時間: 30秒）",
            view=quiz_view
        )

        await quiz_view.wait()

        # 5. 時間切れ（未回答）処理
        if quiz_view.selected_answer is None:
            if difficulty == "難しい":
                refund = int(bet * 0.1)
                loss = -bet + refund
                update_user_quiz_result(user_id, loss, f"クイズ未回答（難しい）: {loss}pt")
                await interaction.edit_original_response(
                    content=f"⏱️ **時間切れ！**\n{interaction.user.display_name}さんは時間内に回答できませんでした。\n"
                            f"難易度「難しい」のため、10%の **{refund} pt** が救済返還されました。", 
                    view=None
                )
            else:
                update_user_quiz_result(user_id, -bet, f"クイズ未回答（{difficulty}）: -{bet}pt")
                await interaction.edit_original_response(
                    content=f"⏱️ **時間切れ！**\n{interaction.user.display_name}さんは時間内に回答できませんでした。\n"
                            f"ベットした **{bet} pt** は全額没収されました。", 
                    view=None
                )
            return

        # 6. 正誤判定＆結果表示（ここで通帳にも自動書き込みします！）
        user_ans = quiz_view.selected_answer
        if user_ans == correct_ans:
            # 正解時
            if difficulty == "簡単":
                reward = int(bet * 0.25)
            elif difficulty == "普通":
                reward = int(bet * 0.5)
            else:
                reward = int(bet * 1.0) # 2倍

            update_user_quiz_result(user_id, reward, f"クイズ正解（{difficulty}）: +{reward}pt")
            await interaction.edit_original_response(
                content=f"🎉 **正解です！！！**\n"
                        f"**挑戦者:** {interaction.user.mention}\n"
                        f"**回答:** 「{user_ans}」は見事正解！\n\n"
                        f"難易度【{difficulty}】をクリアし、**+{reward} pt** を獲得しました！✨",
                view=None
            )
        else:
            # 不正解時
            if difficulty == "難しい":
                refund = int(bet * 0.1)
                loss = -bet + refund
                update_user_quiz_result(user_id, loss, f"クイズ不正解（難しい）: {loss}pt")
                await interaction.edit_original_response(
                    content=f"❌ **不正解...！**\n"
                            f"**挑戦者:** {interaction.user.mention}\n"
                            f"**あなたの回答:** 「{user_ans}」\n"
                            f"**正解:** 「{correct_ans}」でした。\n\n"
                            f"難易度「難しい」の救済ルールにより、10%の **{refund} pt** が手元に戻りました。",
                    view=None
                )
            else:
                update_user_quiz_result(user_id, -bet, f"クイズ不正解（{difficulty}）: -{bet}pt")
                await interaction.edit_original_response(
                    content=f"❌ **不正解...！**\n"
                            f"**挑戦者:** {interaction.user.mention}\n"
                            f"**あなたの回答:** 「{user_ans}」\n"
                            f"**正解:** 「{correct_ans}」でした。\n\n"
                            f"ベットした **{bet} pt** は没収されました。また挑戦してね！",
                    view=None
                )
