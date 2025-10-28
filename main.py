import os, logging
from flask import Flask, request
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
PORT = int(os.environ.get("PORT", 10000))
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL", "https://txt-to-video-leech-uploader-ibj3.onrender.com")

application = Application.builder().token(TOKEN).build()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 Bot is live and connected via webhook!")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"📩 You said: {update.message.text}")

application.add_handler(CommandHandler("start", start))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

@app.route("/")
def home():
    return "✅ RAS Downloader Bot is Live on Render!", 200

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json(force=True)
    logger.info(f"📩 Incoming update: {data}")
    try:
        update = Update.de_json(data, application.bot)
        application.update_queue.put_nowait(update)
        return {"ok": True}
    except Exception as e:
        logger.error(f"❌ Webhook error: {e}")
        return {"ok": False, "error": str(e)}, 400

def main():
    logger.info("🚀 Starting Webhook Server...")
    app.run(host="0.0.0.0", port=PORT)

if __name__ == "__main__":
    main()
