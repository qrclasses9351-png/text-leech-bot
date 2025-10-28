import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from deepseek_python_20251028_59d3bb import AdvancedFileDownloaderBot

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
PORT = int(os.getenv("PORT", "8080"))
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL", "").rstrip("/")

if not BOT_TOKEN:
    raise RuntimeError("❌ TELEGRAM_BOT_TOKEN not set in environment!")
if not RENDER_URL:
    raise RuntimeError("❌ RENDER_EXTERNAL_URL not set! Example: https://your-app-name.onrender.com")

WEBHOOK_PATH = f"/{BOT_TOKEN}"
WEBHOOK_URL = f"{RENDER_URL}{WEBHOOK_PATH}"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Advanced RAS Downloader Webhook Bot चालू है!")

def main():
    print("🚀 Starting Webhook mode bot for Render...")
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        path=WEBHOOK_PATH,
        webhook_url=WEBHOOK_URL,
    )

if __name__ == "__main__":
    main()
