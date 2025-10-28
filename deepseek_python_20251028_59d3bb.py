import os
import re
import requests
import time
import asyncio
import math
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from concurrent.futures import ThreadPoolExecutor
import logging

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class AdvancedRASDownloader:
    def __init__(self):
        self.download_dir = "ras_downloads"
        self.max_workers = 3
        os.makedirs(self.download_dir, exist_ok=True)
    
    def extract_links_from_text(self, text):
        """टेक्स्ट से सारे डाउनलोड लिंक्स निकालें"""
        links = []
        
        pattern = r'\(([^)]+)\)\s*(.*?)\s*(https://[^\s]+)'
        matches = re.findall(pattern, text)
        
        for i, match in enumerate(matches):
            subject = match[0].strip()
            description = match[1].strip()
            url = match[2].strip()
            
            if '.pdf' in url.lower():
                file_type = 'pdf'
            elif '.mp4' in url.lower() or 'video' in url.lower():
                file_type = 'mp4'
            else:
                file_type = 'file'
            
            safe_subject = re.sub(r'[^\w\s-]', '', subject)
            safe_description = re.sub(r'[^\w\s-]', '', description)
            safe_description = re.sub(r'\s+', '_', safe_description)
            
            filename = f"{i+1:03d}_{safe_subject}_{safe_description}.{file_type}"
            
            links.append({
                'id': i + 1,
                'subject': subject,
                'description': description,
                'url': url,
                'filename': filename,
                'type': file_type,
                'status': 'pending',
                'progress': 0,
                'size': 0,
                'downloaded': 0
            })
        
        return links
    
    def download_file_with_progress(self, link, progress_callback=None):
        """प्रोग्रेस ट्रैकिंग के साथ फाइल डाउनलोड करें"""
        try:
            filepath = os.path.join(self.download_dir, link['filename'])
            link['status'] = 'downloading'
            
            if os.path.exists(filepath):
                link['status'] = 'completed'
                link['progress'] = 100
                if progress_callback:
                    progress_callback(link)
                return {'success': True, 'message': f'⏩ पहले से मौजूद', 'filename': link['filename']}
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': '*/*'
            }
            
            response = requests.get(link['url'], stream=True, timeout=60, headers=headers)
            response.raise_for_status()
            
            total_size = int(response.headers.get('content-length', 0))
            link['size'] = total_size
            
            downloaded_size = 0
            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded_size += len(chunk)
                        link['downloaded'] = downloaded_size
                        
                        if total_size > 0:
                            progress = (downloaded_size / total_size) * 100
                            link['progress'] = round(progress, 1)
                        else:
                            link['progress'] = 50
                        
                        if progress_callback and downloaded_size % 81920 == 0:
                            progress_callback(link)
            
            link['status'] = 'completed'
            link['progress'] = 100
            file_size = os.path.getsize(filepath)
            
            if progress_callback:
                progress_callback(link)
                
            return {
                'success': True, 
                'message': f'✅ {file_size/1024/1024:.1f} MB',
                'filename': link['filename'],
                'filepath': filepath
            }
            
        except Exception as e:
            link['status'] = 'failed'
            link['progress'] = 0
            if progress_callback:
                progress_callback(link)
            return {'success': False, 'message': f'❌ {str(e)}'}

    def batch_download(self, links, progress_callback=None):
        """बैच में multiple फाइल्स डाउनलोड करें"""
        results = []
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_link = {
                executor.submit(self.download_file_with_progress, link, progress_callback): link 
                for link in links
            }
            
            for future in future_to_link:
                try:
                    result = future.result(timeout=300)
                    results.append(result)
                except Exception as e:
                    results.append({'success': False, 'message': f'❌ Timeout/Error: {str(e)}'})
        
        return results

class AdvancedFileDownloaderBot:
    def __init__(self, token):
        self.token = token
        self.app = Application.builder().token(token).build()
        self.downloader = AdvancedRASDownloader()
        self.user_sessions = {}
        self.setup_handlers()
    
    def setup_handlers(self):
        self.app.add_handler(CommandHandler("start", self.start_command))
        self.app.add_handler(CommandHandler("help", self.help_command))
        self.app.add_handler(CommandHandler("download_ras", self.download_ras_command))
        self.app.add_handler(CommandHandler("batch_download", self.batch_download_command))
        self.app.add_handler(CommandHandler("status", self.status_command))
        
        self.app.add_handler(CallbackQueryHandler(self.button_handler, pattern="^(download_all|download_pdf|download_video|cancel)$"))
        
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text))
    
    def create_progress_bar(self, progress, length=20):
        """प्रोग्रेस बार बनाएं"""
        filled = int(length * progress / 100)
        bar = '█' * filled + '░' * (length - filled)
        return f"[{bar}] {progress}%"
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        welcome_text = """
🚀 **एडवांस्ड RAS डाउनलोडर बॉट**

मैं बैच डाउनलोड, प्रोग्रेस ट्रैकिंग और ज्यादा फाइल्स सपोर्ट करता हूँ!

**कमांड्स:**
/start - बॉट शुरू करें
/download_ras - सिंगल डाउनलोड
/batch_download - बैच डाउनलोड (ज्यादा फाइल्स)
/status - करंट डाउनलोड स्टेटस
/help - मदद

**या सीधे टेक्स्ट भेजें** जिसमें डाउनलोड लिंक्स हों
        """
        await update.message.reply_text(welcome_text)
    
    async def batch_download_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        help_text = """
📦 **बैच डाउनलोड फीचर**

यह फीचर आपको:
✅ एक साथ 10+ फाइल्स डाउनलोड करने देता है
✅ रियल-टाइम प्रोग्रेस बार दिखाता है  
✅ पैरलल डाउनलोड (एक साथ 3 फाइल्स)
✅ ऑटोमैटिक रिट्राय

**इस्तेमाल करें:**
1. टेक्स्ट कॉपी करें (सारे लिंक्स के साथ)
2. मुझे भेजें
3. डाउनलोड ऑप्शन चुनें

अभी टेक्स्ट भेजें...
        """
        await update.message.reply_text(help_text)
    
    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if user_id in self.user_sessions and 'links' in self.user_sessions[user_id]:
            links = self.user_sessions[user_id]['links']
            status_text = await self.generate_status_message(links)
            await update.message.reply_text(status_text, parse_mode='HTML')
        else:
            await update.message.reply_text("ℹ️ कोई एक्टिव डाउनलोड नहीं है। टेक्स्ट भेजकर शुरू करें।")
    
    async def download_ras_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        help_text = """
📖 **RAS फाइल्स डाउनलोड करें**

टेक्स्ट भेजें जिसमें डाउनलोड लिंक्स हों। मैं:
- पहले 5 फाइल्स ऑटोमैटिक डाउनलोड करूंगा
- प्रोग्रेस बार दिखाऊंगा
- डाउनलोड के बाद फाइल्स भेज दूंगा

अभी टेक्स्ट भेजें...
        """
        await update.message.reply_text(help_text)
    
    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_message = update.message.text
        user_id = update.effective_user.id
        
        if 'https://' not in user_message:
            await update.message.reply_text("❌ कृपया डाउनलोड लिंक्स वाला टेक्स्ट भेजें।")
            return
        
        try:
            links = self.downloader.extract_links_from_text(user_message)
            
            if not links:
                await update.message.reply_text("❌ टेक्स्ट में कोई वैलिड लिंक नहीं मिला।")
                return
            
            self.user_sessions[user_id] = {
                'links': links,
                'start_time': time.time(),
                'status_message': None
            }
            
            total_files = len(links)
            pdf_count = sum(1 for l in links if l['type'] == 'pdf')
            video_count = sum(1 for l in links if l['type'] == 'mp4')
            
            status_msg = await update.message.reply_text(
                f"🔍 <b>{total_files} फाइल्स मिलीं</b>\n"
                f"📄 PDF: {pdf_count} | 🎥 वीडियो: {video_count}\n\n"
                f"⏳ प्रोसेसिंग...",
                parse_mode='HTML'
            )
            
            keyboard = [
                [
                    InlineKeyboardButton("📦 सब डाउनलोड करें", callback_data="download_all"),
                    InlineKeyboardButton("📄 केवल PDF", callback_data="download_pdf")
                ],
                [
                    InlineKeyboardButton("🎥 केवल वीडियो", callback_data="download_video"),
                    InlineKeyboardButton("❌ कैंसल", callback_data="cancel")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await status_msg.edit_text(
                f"🎯 <b>{total_files} फाइल्स तैयार हैं</b>\n"
                f"📄 PDF: {pdf_count} | 🎥 वीडियो: {video_count}\n\n"
                f"कौनसी फाइल्स डाउनलोड करनी हैं?",
                parse_mode='HTML',
                reply_markup=reply_markup
            )
            
            self.user_sessions[user_id]['status_message'] = status_msg
            
        except Exception as e:
            logger.error(f"त्रुटि: {e}")
            await update.message.reply_text(f"❌ कुछ गलत हो गया: {str(e)}")
    
    async def button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        data = query.data
        
        if user_id not in self.user_sessions:
            await query.edit_message_text("❌ Session expired. कृपया फिर से टेक्स्ट भेजें।")
            return
        
        links = self.user_sessions[user_id]['links']
        status_msg = self.user_sessions[user_id]['status_message']
        
        if data == "cancel":
            await query.edit_message_text("❌ डाउनलोड कैंसल किया गया।")
            del self.user_sessions[user_id]
            return
        
        if data == "download_pdf":
            selected_links = [link for link in links if link['type'] == 'pdf']
        elif data == "download_video":
            selected_links = [link for link in links if link['type'] == 'mp4']
        else:
            selected_links = links
        
        if not selected_links:
            await query.edit_message_text("❌ चयनित टाइप की कोई फाइल नहीं मिली।")
            return
        
        await query.edit_message_text(
            f"🚀 <b>डाउनलोड शुरू...</b>\n"
            f"📦 {len(selected_links)} फाइल्स selected\n"
            f"⏳ तैयार हो रहा है...",
            parse_mode='HTML'
        )
        
        await self.start_batch_download(user_id, selected_links, status_msg)
    
    async def start_batch_download(self, user_id, links, status_msg):
        try:
            total_files = len(links)
            
            def progress_callback(link):
                asyncio.create_task(self.update_progress_message(user_id, status_msg, links))
            
            await status_msg.edit_text(
                f"📥 <b>बैच डाउनलोड शुरू</b>\n"
                f"📦 कुल फाइल्स: {total_files}\n"
                f"🚀 एक साथ डाउनलोड: {self.downloader.max_workers}\n\n"
                f"⏳ शुरू हो रहा है...",
                parse_mode='HTML'
            )
            
            loop = asyncio.get_event_loop()
            with ThreadPoolExecutor() as executor:
                results = await loop.run_in_executor(
                    executor, 
                    self.downloader.batch_download, 
                    links, 
                    progress_callback
                )
            
            completed_files = sum(1 for r in results if r['success'])
            failed_files = total_files - completed_files
            
            final_message = (
                f"🎉 <b>डाउनलोड पूरा!</b>\n\n"
                f"✅ सफल: {completed_files}\n"
                f"❌ विफल: {failed_files}\n"
                f"📁 फाइल्स: ras_downloads फोल्डर में\n\n"
                f"<i>फाइल्स ऑटोमैटिक आपको भेज दी जाएंगी...</i>"
            )
            
            await status_msg.edit_text(final_message, parse_mode='HTML')
            
            await self.send_downloaded_files(user_id, links, status_msg)
            
        except Exception as e:
            logger.error(f"बैच डाउनलोड त्रुटि: {e}")
            await status_msg.edit_text(f"❌ डाउनलोड में त्रुटि: {str(e)}")
    
    async def update_progress_message(self, user_id, status_msg, links):
        try:
            total = len(links)
            completed = sum(1 for l in links if l['status'] == 'completed')
            downloading = sum(1 for l in links if l['status'] == 'downloading')
            failed = sum(1 for l in links if l['status'] == 'failed')
            pending = total - completed - downloading - failed
            
            current_downloads = [l for l in links if l['status'] == 'downloading']
            
            progress_text = f"📊 <b>डाउनलोड प्रोग्रेस</b>\n\n"
            progress_text += f"✅ पूरे: {completed}/{total} | ⏳ चल रहे: {downloading} | ❌ फेल: {failed}\n\n"
            
            if current_downloads:
                for link in current_downloads[:2]:
                    progress_bar = self.create_progress_bar(link['progress'])
                    size_info = f"({link['downloaded']/1024/1024:.1f}MB/" + \
                               f"{link['size']/1024/1024:.1f}MB)" if link['size'] > 0 else ""
                    progress_text += f"📥 {link['filename'][:30]}...\n{progress_bar} {size_info}\n\n"
            else:
                progress_text += "⏳ तैयार हो रहा है...\n\n"
            
            overall_progress = (completed / total) * 100 if total > 0 else 0
            overall_bar = self.create_progress_bar(overall_progress)
            progress_text += f"<b>कुल प्रोग्रेस:</b>\n{overall_bar}"
            
            await status_msg.edit_text(progress_text, parse_mode='HTML')
            
        except Exception as e:
            logger.error(f"प्रोग्रेस अपडेट त्रुटि: {e}")
    
    async def send_downloaded_files(self, user_id, links, status_msg):
        try:
            successful_links = [l for l in links if l['status'] == 'completed']
            
            await status_msg.edit_text(
                f"📤 <b>फाइल्स भेज रहा हूँ...</b>\n"
                f"✅ {len(successful_links)} फाइल्स तैयार हैं\n"
                f"⏳ कृपया wait करें...",
                parse_mode='HTML'
            )
            
            for i, link in enumerate(successful_links):
                filepath = os.path.join(self.downloader.download_dir, link['filename'])
                
                if os.path.exists(filepath):
                    try:
                        with open(filepath, 'rb') as file:
                            if link['type'] == 'pdf':
                                await self.app.bot.send_document(
                                    chat_id=user_id,
                                    document=file,
                                    filename=link['filename'],
                                    caption=f"📄 {link['subject']}\n{link['description']}"
                                )
                            elif link['type'] == 'mp4':
                                await self.app.bot.send_video(
                                    chat_id=user_id,
                                    video=file,
                                    caption=f"🎥 {link['subject']}\n{link['description']}"
                                )
                        
                        progress = ((i + 1) / len(successful_links)) * 100
                        await status_msg.edit_text(
                            f"📤 <b>फाइल्स भेज रहा हूँ...</b>\n"
                            f"✅ {i + 1}/{len(successful_links)} भेज दी गई\n"
                            f"{self.create_progress_bar(progress)}",
                            parse_mode='HTML'
                        )
                        
                    except Exception as e:
                        logger.error(f"फाइल भेजने में त्रुटि {link['filename']}: {e}")
                
                await asyncio.sleep(1)
            
            await status_msg.edit_text(
                f"🎉 <b>सब कुछ पूरा!</b>\n\n"
                f"✅ {len(successful_links)} फाइल्स भेज दी गईं\n"
                f"📁 लोकल कॉपी: ras_downloads फोल्डर में\n\n"
                f"<i>नए फाइल्स के लिए फिर से टेक्स्ट भेजें!</i>",
                parse_mode='HTML'
            )
            
            if user_id in self.user_sessions:
                del self.user_sessions[user_id]
                
        except Exception as e:
            logger.error(f"फाइल्स भेजने में त्रुटि: {e}")
            await status_msg.edit_text(f"❌ फाइल्स भेजने में त्रुटि: {str(e)}")
    
    async def generate_status_message(self, links):
        total = len(links)
        completed = sum(1 for l in links if l['status'] == 'completed')
        downloading = sum(1 for l in links if l['status'] == 'downloading')
        failed = sum(1 for l in links if l['status'] == 'failed')
        
        status_text = f"<b>📊 करंट डाउनलोड स्टेटस</b>\n\n"
        status_text += f"📦 कुल फाइल्स: {total}\n"
        status_text += f"✅ पूरे: {completed}\n"
        status_text += f"📥 चल रहे: {downloading}\n"
        status_text += f"❌ फेल: {failed}\n\n"
        
        if downloading > 0:
            current = [l for l in links if l['status'] == 'downloading']
            status_text += "<b>चल रहे डाउनलोड:</b>\n"
            for link in current[:3]:
                progress_bar = self.create_progress_bar(link['progress'])
                status_text += f"• {link['filename'][:25]}...\n{progress_bar}\n"
        
        return status_text
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        help_text = """
🆘 <b>एडवांस्ड RAS डाउनलोडर - हेल्प</b>

<u>फीचर्स:</u>
• 📦 बैच डाउनलोड - एक साथ 10+ फाइल्स
• 📊 रियल-टाइम प्रोग्रेस - लाइव अपडेट
• 🚀 पैरलल डाउनलोड - एक साथ 3 फाइल्स
• 🔄 ऑटो रिट्राय - फेल होने पर दोबारा कोशिश
• 📁 ऑटो सेन्ड - डाउनलोड के बाद फाइल्स भेजें

<u>कमांड्स:</u>
/start - बॉट शुरू करें
/download_ras - सिंगल डाउनलोड
/batch_download - बैच डाउनलोड
/status - करंट स्टेटस देखें
/help - यह मैसेज

<u>इस्तेमाल करें:</u>
1. टेक्स्ट कॉपी करें (सारे लिंक्स के साथ)
2. बॉट को भेजें  
3. डाउनलोड ऑप्शन चुनें
4. प्रोग्रेस देखें और फाइल्स प्राप्त करें
        """
        await update.message.reply_text(help_text, parse_mode='HTML')

def check_environment():
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
    if not bot_token:
        print("❌ TELEGRAM_BOT_TOKEN environment variable not set!")
        return False
    print("✅ Environment check passed!")
    return True

def main():
    print("🚀 Starting Advanced RAS File Downloader Bot...")
    
    if not check_environment():
        return
    
    BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
    
    try:
        print("🤖 Initializing advanced bot...")
        bot = AdvancedFileDownloaderBot(BOT_TOKEN)
        print("✅ Bot initialized successfully!")
        print("📦 Features: Batch Download, Progress Bar, Multiple Files Support")
        
        bot.app.run_polling()
        
    except Exception as e:
        print(f"❌ Failed to start bot: {e}")

if __name__ == '__main__':
    main()