import os
import re
import requests
import logging
from telegram import Update, Document
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# =================== LOGGER ===================
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# =================== ENV CHECK ===================
def check_environment():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        print("❌ TELEGRAM_BOT_TOKEN not found! Add it in Render Environment Variables.")
        return None
    print("✅ Environment check passed!")
    print(f"🤖 Bot token: {token[:10]}...")
    return token

# =================== BOT CLASS ===================
class RASFileDownloader:
    def __init__(self, token):
        self.app = Application.builder().token(token).build()
        self.app.add_handler(CommandHandler("start", self.start))
        self.app.add_handler(CommandHandler("help", self.help))
        self.app.add_handler(MessageHandler(filters.Document.TXT, self.handle_txt))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text))

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "🤖 **RAS File Downloader Bot Ready!**\n\n"
            "📄 Send me:\n"
            "1️⃣ Text containing PDF/MP4 links\n"
            "2️⃣ Or upload a `.txt` file with links\n\n"
            "मैं सभी फाइलें डाउनलोड करके सीधे Telegram में भेज दूँगा ✅"
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

    # =================== HANDLE TEXT ===================
    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = update.message.text
        links = self.extract_links(text)
        if not links:
            await update.message.reply_text("❌ कोई सही लिंक नहीं मिला।")
            return
        await self.process_links(links, update, context)

    # =================== HANDLE TXT FILE ===================
    async def handle_txt(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        document: Document = update.message.document
        file_name = document.file_name
        await update.message.reply_text(f"📄 Received `{file_name}` — reading links...")

        file = await document.get_file()
        txt_path = f"downloads/{file_name}"
        os.makedirs("downloads", exist_ok=True)
        await file.download_to_drive(txt_path)

        with open(txt_path, "r", encoding="utf-8") as f:
            content = f.read()

        os.remove(txt_path)
        links = self.extract_links(content)

        if not links:
            await update.message.reply_text("❌ TXT फाइल में कोई वैध लिंक नहीं मिला।")
            return

        await self.process_links(links, update, context)

    # =================== DOWNLOAD + SEND ===================
    async def process_links(self, links, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.message.chat_id
        await update.message.reply_text(f"🔍 {len(links)} लिंक मिले — डाउनलोड शुरू...")

        for link in links:
            url = link["url"]
            filename = link["filename"]

            try:
                filepath = self.download_file(url, filename)
                if filepath:
                    await context.bot.send_document(chat_id=chat_id, document=open(filepath, "rb"))
                    os.remove(filepath)
                    logger.info(f"Uploaded and removed {filename}")
                else:
                    await update.message.reply_text(f"⚠️ डाउनलोड असफल: {url}")
            except Exception as e:
                await update.message.reply_text(f"❌ Error sending {filename}: {e}")

        await update.message.reply_text("✅ सभी फाइलें Telegram में भेज दी गईं!")

    # =================== LINK EXTRACTION ===================
    def extract_links(self, text):
        pattern = r"(https?://[^\s]+)"
        urls = re.findall(pattern, text)
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

    # =================== FILE DOWNLOAD ===================
    def download_file(self, url, filename):
        os.makedirs("downloads", exist_ok=True)
        filepath = os.path.join("downloads", filename)
        try:
            with requests.get(url, stream=True, headers={"User-Agent": "Mozilla/5.0"}, timeout=30) as r:
                r.raise_for_status()
                with open(filepath, "wb") as f:
                    for chunk in r.iter_content(8192):
                        f.write(chunk)
            return filepath
        except Exception as e:
            logger.error(f"Download failed: {e}")
            return None

# =================== MAIN FUNCTION ===================
def main():
    print("🚀 Starting RAS File Downloader Bot (Auto Upload + TXT Support)...")
    token = check_environment()
    if not token:
        return

    bot = RASFileDownloader(token)
    render_url = os.getenv("RENDER_EXTERNAL_URL")
    port = int(os.environ.get("PORT", 10000))

    if render_url:
        webhook_url = f"{render_url}/{token}"
        print(f"🌐 Setting webhook: {webhook_url}")
        bot.app.run_webhook(listen="0.0.0.0", port=port, webhook_url=webhook_url)
    else:
        print("🌀 Running in polling mode (local testing)")
        bot.app.run_polling()

if __name__ == "__main__":
    main()
