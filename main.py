import os
import re
import requests
import logging
from flask import Flask, request
from telegram import Update, Document
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Flask app
flask_app = Flask(__name__)

# ---------- Environment ----------
def check_environment():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    render_url = os.getenv("RENDER_EXTERNAL_URL")
    if not token:
        print("❌ TELEGRAM_BOT_TOKEN not set")
        return None, None
    print("✅ Environment OK")
    return token, render_url


# ---------- Telegram Bot ----------
class RASDownloader:
    def __init__(self, token):
        self.app = Application.builder().token(token).build()
        self.app.add_handler(CommandHandler("start", self.start))
        self.app.add_handler(CommandHandler("help", self.help))
        self.app.add_handler(MessageHandler(filters.Document.TXT, self.txt_handler))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.text_handler))

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "🤖 *RAS Downloader Active!*\nSend text or `.txt` file with links.",
            parse_mode="Markdown"
        )

    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("📘 Send .txt or direct PDF/MP4 link to download & auto-upload.")

    async def text_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = update.message.text
        links = self.extract_links(text)
        if not links:
            await update.message.reply_text("❌ कोई वैध लिंक नहीं मिला।")
            return
        await self.process_links(links, update, context)

    async def txt_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        doc: Document = update.message.document
        file = await doc.get_file()
        path = f"downloads/{doc.file_name}"
        os.makedirs("downloads", exist_ok=True)
        await file.download_to_drive(path)
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        os.remove(path)
        links = self.extract_links(text)
        if not links:
            await update.message.reply_text("❌ TXT में कोई लिंक नहीं मिला।")
            return
        await self.process_links(links, update, context)

    async def process_links(self, links, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.message.chat_id
        await update.message.reply_text(f"🔍 {len(links)} लिंक मिले, डाउनलोड शुरू...")
        for link in links:
            url, filename = link["url"], link["filename"]
            file_path = self.download(url, filename)
            if file_path:
                await context.bot.send_document(chat_id=chat_id, document=open(file_path, "rb"))
                os.remove(file_path)
        await update.message.reply_text("✅ सभी फाइलें भेज दी गईं!")

    def extract_links(self, text):
        urls = re.findall(r"(https?://[^\s]+)", text)
        links = []
        for url in urls:
            ext = ".pdf" if ".pdf" in url else ".mp4" if ".mp4" in url else None
            if not ext:
                continue
            filename = url.split("/")[-1].split("?")[0]
            if not filename.endswith(ext):
                filename += ext
            links.append({"url": url, "filename": filename})
        return links

    def download(self, url, name):
        try:
            os.makedirs("downloads", exist_ok=True)
            file_path = f"downloads/{name}"
            with requests.get(url, stream=True, headers={"User-Agent": "Mozilla/5.0"}) as r:
                r.raise_for_status()
                with open(file_path, "wb") as f:
                    for chunk in r.iter_content(8192):
                        f.write(chunk)
            return file_path
        except Exception as e:
            logger.error(f"Download error: {e}")
            return None


# ---------- Flask webhook ----------
@flask_app.route("/", methods=["GET"])
def home():
    return "✅ Bot is Live!", 200


@flask_app.route("/webhook", methods=["POST"])
def webhook():
    try:
        data = request.get_json(force=True)
        update = Update.de_json(data, bot_instance.app.bot)
        bot_instance.app.update_queue.put_nowait(update)
        return {"ok": True}, 200
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return {"error": str(e)}, 500


# ---------- Webhook Setup ----------
def setup_webhook(token, render_url):
    webhook_url = f"{render_url}/webhook"
    print(f"🌐 Setting webhook: {webhook_url}")
    requests.get(f"https://api.telegram.org/bot{token}/deleteWebhook")
    r = requests.get(f"https://api.telegram.org/bot{token}/setWebhook?url={webhook_url}")
    print("🔁 Webhook response:", r.text)


# ---------- Main ----------
def main():
    global bot_instance
    print("🚀 Starting RAS Downloader (Webhook + TXT Upload + Auto Send)...")

    token, render_url = check_environment()
    if not token or not render_url:
        return

    bot_instance = RASDownloader(token)
    setup_webhook(token, render_url)

    port = int(os.environ.get("PORT", 10000))
    bot_instance.app.run_webhook(listen="0.0.0.0", port=port, webhook_url=f"{render_url}/webhook")


if __name__ == "__main__":
    main()
