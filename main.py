import os
import re
import requests
import logging
from telegram import Update, Document
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ========== Logging ==========
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


def check_environment():
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
    render_url = os.getenv('RENDER_EXTERNAL_URL')

    if not bot_token:
        print("❌ TELEGRAM_BOT_TOKEN not set!")
        return False
    if not render_url:
        print("❌ RENDER_EXTERNAL_URL not set!")
        return False

    print("✅ Environment check passed!")
    return True


class FileDownloaderBot:
    def __init__(self, token):
        self.token = token
        self.app = Application.builder().token(token).build()
        self.setup_handlers()

    def setup_handlers(self):
        self.app.add_handler(CommandHandler("start", self.start_command))
        self.app.add_handler(CommandHandler("help", self.help_command))
        self.app.add_handler(MessageHandler(filters.Document.ALL, self.handle_file))  # 🧩 For txt file
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text))

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "🤖 Bot ready!\nSend me text **or a .txt file** containing links to download."
        )

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "📘 Send either:\n"
            "1️⃣ A message with direct links (like https://example.com/file.pdf)\n"
            "2️⃣ Or upload a .txt file containing one link per line"
        )

    # 🧾 Handle plain text messages
    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = update.message.text
        links = self.extract_links(text)

        if not links:
            await update.message.reply_text("⚠️ No valid links found.")
            return

        await self.process_links(update, links)

    # 📄 Handle uploaded .txt file
    async def handle_file(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        doc: Document = update.message.document

        if not doc.file_name.lower().endswith(".txt"):
            await update.message.reply_text("⚠️ Please send a valid .txt file only.")
            return

        await update.message.reply_text(f"📂 Received file: {doc.file_name}\nReading links...")

        # Download the .txt file to server
        file = await doc.get_file()
        file_path = f"downloads/{doc.file_name}"
        os.makedirs("downloads", exist_ok=True)
        await file.download_to_drive(file_path)

        # Read all links from text file
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        links = self.extract_links(content)
        if not links:
            await update.message.reply_text("❌ No valid links found in your text file.")
            return

        await self.process_links(update, links)

    # 🧩 Extract https links
    def extract_links(self, text):
        pattern = r'(https://[^\s]+)'
        return re.findall(pattern, text)

    # 🚀 Download and send files
    async def process_links(self, update, links):
        status_msg = await update.message.reply_text(f"🔍 Found {len(links)} links. Starting download...")
        success = 0

        for i, url in enumerate(links[:10], 1):  # Limit to first 10 links
            filename = self.get_filename_from_url(url)
            await status_msg.edit_text(f"⬇️ Downloading {i}/{len(links)}: {filename}")

            file_path = self.download_file(url, filename)
            if file_path:
                try:
                    await update.message.reply_document(open(file_path, "rb"))
                    success += 1
                except Exception as e:
                    await update.message.reply_text(f"⚠️ Error sending {filename}: {e}")
            else:
                await update.message.reply_text(f"❌ Failed: {url}")

        await status_msg.edit_text(f"✅ Done! {success}/{len(links)} files sent successfully.")

    def get_filename_from_url(self, url):
        name = url.split("/")[-1].split("?")[0]
        if not re.search(r'\.\w+$', name):
            name += ".bin"
        return name

    def download_file(self, url, filename):
        try:
            os.makedirs("downloads", exist_ok=True)
            path = os.path.join("downloads", filename)
            headers = {"User-Agent": "Mozilla/5.0"}
            r = requests.get(url, headers=headers, stream=True, timeout=60)
            if r.status_code != 200:
                logger.warning(f"Download failed {r.status_code} for {url}")
                return None
            with open(path, "wb") as f:
                for chunk in r.iter_content(8192):
                    if chunk:
                        f.write(chunk)
            return path
        except Exception as e:
            logger.error(f"Error downloading {url}: {e}")
            return None


def main():
    print("🚀 Starting File Downloader Bot (txt supported)...")

    if not check_environment():
        return

    BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    RENDER_URL = os.getenv("RENDER_EXTERNAL_URL").rstrip("/")
    PORT = int(os.getenv("PORT", "8080"))

    bot = FileDownloaderBot(BOT_TOKEN)

    bot.app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=BOT_TOKEN,
        webhook_url=f"{RENDER_URL}/{BOT_TOKEN}",
    )


if __name__ == "__main__":
    main()
