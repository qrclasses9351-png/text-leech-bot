import os
import re
import requests
import logging
from telegram import Update, Document
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ========== LOGGER ==========
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# ========== ENV CHECK ==========
def check_environment():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        print("❌ TELEGRAM_BOT_TOKEN not found! Add it in Render Environment Variables.")
        return None
    print("✅ Environment check passed!")
    print(f"🤖 Bot token: {token[:10]}...")
    return token

# ========== BOT CLASS ==========
class RASFileDownloader:
    def __init__(self, token):
        self.app = Application.builder().token(token).build()
        self.app.add_handler(CommandHandler("start", self.start))
        self.app.add_handler(CommandHandler("help", self.help))
        self.app.add_handler(MessageHandler(filters.Document.TXT, self.handle_txt))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text))

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "🤖 **RAS Downloader Ready!**\n\n"
            "📄 Send text with links OR upload a `.txt` file containing PDF/MP4 URLs.\n\n"
            "मैं लिंक से फाइल डाउनलोड करके सीधे Telegram में भेज दूँगा ✅"
        )

    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "📘 *Help:*\n\n"
            "- Send direct links (PDF/MP4)\n"
            "- Or upload `.txt` file containing multiple links\n\n"
            "Example:\n"
            "(Maths) https://example.com/file.pdf\n"
            "(Physics) https://example.com/video.mp4"
        )

    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = update.message.text
        links = self.extract_links(text)
        if not links:
            await update.message.reply_text("❌ कोई वैध लिंक नहीं मिला।")
            return
        await self.process_links(links, update, context)

    async def handle_txt(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        document: Document = update.message.document
        await update.message.reply_text("📄 TXT फाइल मिली — पढ़ रहा हूँ...")
        os.makedirs("downloads", exist_ok=True)
        file_path = f"downloads/{document.file_name}"
        file = await document.get_file()
        await file.download_to_drive(file_path)

        with open(file_path, "r", encoding="utf-8") as f:
            text = f.read()
        os.remove(file_path)

        links = self.extract_links(text)
        if not links:
            await update.message.reply_text("❌ TXT फाइल में कोई लिंक नहीं मिला।")
            return

        await self.process_links(links, update, context)

    async def process_links(self, links, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.message.chat_id
        await update.message.reply_text(f"🔍 {len(links)} लिंक मिले — डाउनलोड शुरू...")
        for link in links:
            url, filename = link["url"], link["filename"]
            try:
                filepath = self.download_file(url, filename)
                if filepath:
                    await context.bot.send_document(chat_id=chat_id, document=open(filepath, "rb"))
                    os.remove(filepath)
                    logger.info(f"✅ Sent: {filename}")
                else:
                    await update.message.reply_text(f"⚠️ डाउनलोड असफल: {url}")
            except Exception as e:
                await update.message.reply_text(f"❌ Error sending {filename}: {e}")
        await update.message.reply_text("✅ सभी फाइलें Telegram में भेज दी गईं!")

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

    def download_file(self, url, filename):
        try:
            os.makedirs("downloads", exist_ok=True)
            filepath = os.path.join("downloads", filename)
            with requests.get(url, stream=True, headers={"User-Agent": "Mozilla/5.0"}, timeout=30) as r:
                r.raise_for_status()
                with open(filepath, "wb") as f:
                    for chunk in r.iter_content(8192):
                        f.write(chunk)
            return filepath
        except Exception as e:
            logger.error(f"Download failed: {e}")
            return None

# ========== AUTO WEBHOOK ==========
def setup_webhook(token):
    render_url = os.getenv("RENDER_EXTERNAL_URL")  # ✅ यह लाइन जोड़ो

    if not render_url:
        print("🌀 Running in polling mode (local)")
        return None

    webhook_url = f"{render_url}/webhook"  # ✅ अब variable defined है

    print("🔁 Resetting webhook...")
    requests.get(f"https://api.telegram.org/bot{token}/deleteWebhook")

    print(f"🌐 Setting webhook to: {webhook_url}")
    resp = requests.get(f"https://api.telegram.org/bot{token}/setWebhook?url={webhook_url}")
    print(f"Webhook response: {resp.text}")
    if '"ok":true' in resp.text:
        print("✅ Webhook active and working!")
    else:
        print("⚠️ Webhook setup failed!")

    return webhook_url

# ========== MAIN ==========
def main():
    print("🚀 Starting RAS Downloader Bot (Auto Webhook + TXT Upload)...")
    token = check_environment()
    if not token:
        return

    setup_webhook(token)
    bot = RASFileDownloader(token)

    port = int(os.environ.get("PORT", 10000))
    render_url = os.getenv("RENDER_EXTERNAL_URL")

    if render_url:
        bot.app.run_webhook(listen="0.0.0.0", port=port, webhook_url=f"{render_url}/{token}")
    else:
        bot.app.run_polling()

if __name__ == "__main__":
    main()
