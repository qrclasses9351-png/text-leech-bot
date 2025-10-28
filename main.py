import os
import re
import requests
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def check_environment():
    """Check if all required environment variables are set"""
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
    
    if not bot_token:
        print("❌ CRITICAL ERROR: TELEGRAM_BOT_TOKEN environment variable not set!")
        print("📝 Please set TELEGRAM_BOT_TOKEN in Render.com Environment Variables")
        print("🔧 Steps to fix:")
        print("   1. Go to your Render.com dashboard")
        print("   2. Click on your Web Service")
        print("   3. Go to 'Environment' section")
        print("   4. Add TELEGRAM_BOT_TOKEN with your bot token")
        print("   5. Manual redeploy")
        return False
    
    print(f"✅ Environment check passed!")
    print(f"🤖 Bot token: {bot_token[:10]}...")
    return True

class FileDownloaderBot:
    def __init__(self, token):
        self.token = token
        self.app = Application.builder().token(token).build()
        self.setup_handlers()
        
    def setup_handlers(self):
        self.app.add_handler(CommandHandler("start", self.start_command))
        self.app.add_handler(CommandHandler("help", self.help_command))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text))
        
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        welcome_text = """
🤖 **RAS File Downloader Bot Started!**

I can download PDF and video files from text content.

Send me text with download links or use /help for instructions.
        """
        await update.message.reply_text(welcome_text)
        
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        help_text = """
📖 **How to use:**

1. Send me text containing download links
2. I will extract and process all PDF/video links
3. Files will be downloaded automatically

**Example format:**
(Subject) Part 1 || Topic || Date: https://example.com/file.pdf

**Commands:**
/start - Start bot
/help - Show this help
        """
        await update.message.reply_text(help_text)
    
    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_message = update.message.text
        
        if 'https://' not in user_message:
            await update.message.reply_text("❌ Please send text containing download links.")
            return
        
        try:
            # Extract links
            links = self.extract_links(user_message)
            
            if not links:
                await update.message.reply_text("❌ No valid links found in the text.")
                return
            
            status_msg = await update.message.reply_text(f"🔍 Found {len(links)} links. Processing...")
            
            # Process links
            success_count = 0
            for i, link in enumerate(links[:5], 1):  # Limit to 5 files
                await status_msg.edit_text(f"📥 Downloading {i}/{len(links[:5])}: {link['name'][:30]}...")
                
                if self.download_file(link['url'], link['filename']):
                    success_count += 1
            
            await status_msg.edit_text(f"✅ Download complete! {success_count}/{len(links[:5])} files downloaded successfully.")
            
        except Exception as e:
            logger.error(f"Error: {e}")
            await update.message.reply_text(f"❌ Error processing your request: {str(e)}")
    
    def extract_links(self, text):
        """Extract download links from text"""
        links = []
        pattern = r'\(([^)]+)\)\s*(.*?)\s*(https://[^\s]+)'
        
        matches = re.findall(pattern, text)
        for match in matches:
            subject = match[0].strip()
            description = match[1].strip()
            url = match[2].strip()
            
            # Create filename
            clean_name = re.sub(r'[^\w\s-]', '', f"{subject}_{description}")
            clean_name = re.sub(r'[-\s]+', '_', clean_name)
            filename = f"{clean_name}.pdf" if '.pdf' in url.lower() else f"{clean_name}.mp4"
            
            links.append({
                'name': f"{subject} - {description}",
                'url': url,
                'filename': filename
            })
        
        return links
    
    def download_file(self, url, filename):
        """Download file from URL"""
        try:
            os.makedirs('downloads', exist_ok=True)
            filepath = os.path.join('downloads', filename)
            
            headers = {'User-Agent': 'Mozilla/5.0'}
            response = requests.get(url, stream=True, timeout=30, headers=headers)
            response.raise_for_status()
            
            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            logger.info(f"Downloaded: {filename}")
            return True
            
        except Exception as e:
            logger.error(f"Download failed {url}: {e}")
            return False

def main():
    print("🚀 Starting RAS File Downloader Bot...")
    print("🔧 Checking environment...")
    
    # Check environment first
    if not check_environment():
        return
    
    # Get bot token
    BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
    
    try:
        print("🤖 Initializing bot...")
        bot = FileDownloaderBot(BOT_TOKEN)
        print("✅ Bot initialized successfully!")
        print("🔗 Bot is now running...")
        
        # Run bot
        bot.app.run_polling()
        
    except Exception as e:
        print(f"❌ Failed to start bot: {e}")
        print("💡 Troubleshooting tips:")
        print("   - Check if TELEGRAM_BOT_TOKEN is correct")
        print("   - Ensure internet connectivity")
        print("   - Check Render.com logs for details")

if __name__ == '__main__':
    main()
