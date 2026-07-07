import os
import asyncio
from flask import Flask
from thread import Thread
import discord
from discord.ext import commands

# 1. Webサーバー（UptimeRobotなどの死活監視用）の設定
app = Flask('')

@app.route('/')
def home():
    return "Bot is alive!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

# 2. Discord Botの設定
# すべてのインテントを有効にする
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"ログインしました: {bot.user.name} (ID: {bot.user.id})")
    print("Botは正常に起動しています。")

# サンプルコマンド (!ping とチャットに入力すると Pong! と返す)
@bot.command()
async def ping(ctx):
    await ctx.send("Pong!")

# 3. メインの起動処理
if __name__ == "__main__":
    # Webサーバーをバックグラウンドで起動
    keep_alive()
    
    # 環境変数からトークンを取得してBotを起動
    token = os.getenv("DISCORD_BOT_TOKEN")
    if token:
        bot.run(token)
    else:
        print("エラー: 環境変数 'DISCORD_BOT_TOKEN' が設定されていません。")