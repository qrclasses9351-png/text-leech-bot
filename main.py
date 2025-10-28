import os
import re
import requests
import logging
from flask import Flask, request
from telegram import Update, Document
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ---------- Logging ----------
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------- Flask App ----------
flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return "✅ RAS Downloader Bot is Live!", 200

@flask_app.route('/webhook', methods=['POST'])
def webhook():
    return "OK", 200

# ---------- Env Check ----------
def check_environment():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        print("❌ TELEGRAM_BOT_TOKEN missing in environment!")
        return None
    print("✅ Environment OK | Bot Token:", token[:10])
    return token

# ---------- Bot Class ----------
class RASDownloader:
    def __init__(self, token):
        self.app = Application.builder().token(token).build()
        self.app.add_handler(CommandHandler("start", self.start))
        self.app.add_handler(CommandHandler("help", self.help))
        self.app.add_handler(MessageHandler(filters.Document.TXT, self.txt_handler))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.text_handler))

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("🤖 *RAS Downloader Ready!*\nSend .txt file or direct PDF/MP4 links to download & upload.", parse_mode="Markdown")

    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("📘 Send text containing links or upload `.txt` file.\nExample:\nhttps://example.com/video.mp4")

    async def text_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = update.message.text
        links = self.extract_links(text)
        if not links:
            await update.message.reply_text("❌ कोई वैध लिंक नहीं मिला।")
            return
        await self.process_links(links, update, context)

    async def txt_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        document: Document = update.message.document
        file = await document.get_file()
        os.makedirs("downloads", exist_ok=True)
        path = f"downloads/{document.file_name}"
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
            if not ext: continue
            name = url.split("/")[-1].split("?")[0]
            if not name.endswith(ext): name += ext
            links.append({"url": url, "filename": name})
        return links

    def download(self, url, name):
        try:
            path = f"downloads/{name}"
            os.makedirs("downloads", exist_ok=True)
            r = requests.get(url, stream=True, headers={"User-Agent": "Mozilla/5.0"})
            r.raise_for_status()
            with open(path, "wb") as f:
                for chunk in r.iter_content(8192):
                    f.write(chunk)
            return path
        except Exception as e:
            logger.error(f"Download failed: {e}")
            return None

# ---------- Setup Webhook ----------
def setup_webhook(token):
    render_url = os.getenv("RENDER_EXTERNAL_URL")
    if not render_url:
        print("🌀 Running in polling mode")
        return None
    webhook_url = f"{render_url}/webhook"
    print(f"🌐 Setting webhook to: {webhook_url}")
    requests.get(f"https://api.telegram.org/bot{token}/deleteWebhook")
    r = requests.get(f"https://api.telegram.org/bot{token}/setWebhook?url={webhook_url}")
    print("Webhook response:", r.text)
    return webhook_url

# ---------- Main ----------
def main():
    print("🚀 Starting RAS Downloader Bot (Webhook + TXT + Upload)...")
    token = check_environment()
    if not token: return
    setup_webhook(token)

    bot = RASDownloader(token)
    port = int(os.environ.get("PORT", 10000))
    render_url = os.getenv("RENDER_EXTERNAL_URL")

    if render_url:
        bot.app.run_webhook(listen="0.0.0.0", port=port, webhook_url=f"{render_url}/webhook")
    else:
        bot.app.run_polling()

if __name__ == "__main__":
    main()
