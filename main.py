"""
main_fixed_mode_B.py

Mode B - Queue-based background workers for processing links (m3u8, pdf, others).
Features:
- When a .txt file is received, bot parses all URLs and enqueues them.
- A set of background worker tasks consume the queue and perform downloads/conversions.
- ffmpeg runs as async subprocess with -c copy and -loglevel error, limited by an ffmpeg semaphore.
- Bot does not block while conversions happen; it replies to user with progress messages.
- Basic error handling and cleanup of downloaded files after upload.

Usage:
- set environment variable TELEGRAM_TOKEN with your bot token.
- ensure ffmpeg is available in PATH on the host (ffmpeg -version).
- install requirements: python-telegram-bot, httpx, aiofiles

This file is intended as a drop-in replacement for your project's main.py (mode B queue).
"""

import os
import asyncio
import logging
import pathlib
import shlex
from typing import List

import aiofiles
import httpx
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters

# ---------- Configuration ----------
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN") or "YOUR_TOKEN_HERE"
DOWNLOADS_DIR = pathlib.Path("downloads")
MAX_WORKERS = int(os.environ.get("MAX_WORKERS", "3"))  # number of background worker consumers
MAX_CONCURRENT_FFMPEG = int(os.environ.get("MAX_CONCURRENT_FFMPEG", "2"))
HTTPX_TIMEOUT = float(os.environ.get("HTTPX_TIMEOUT", "120"))
BATCH_MESSAGE_INTERVAL = 10  # seconds between status messages to avoid spamming

# ---------- Logging ----------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# create downloads dir
DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)

# ---------- Helper functions ----------
async def download_file_async(url: str, output_path: str, client: httpx.AsyncClient):
    out_path = pathlib.Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    async with client.stream("GET", url) as resp:
        resp.raise_for_status()
        async with aiofiles.open(out_path, "wb") as f:
            async for chunk in resp.aiter_bytes(chunk_size=65536):
                await f.write(chunk)
    return str(out_path)


async def convert_m3u8_async(url: str, output_path: str, timeout: int = 0):
    """Non-blocking ffmpeg convert (m3u8 -> mp4) using -c copy where possible."""
    out_dir = pathlib.Path(output_path).parent
    out_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        url,
        "-c",
        "copy",
        "-y",
        output_path,
    ]

    proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE)

    try:
        if timeout and timeout > 0:
            await asyncio.wait_for(proc.wait(), timeout=timeout)
        else:
            await proc.wait()
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise RuntimeError("ffmpeg timeout")

    if proc.returncode != 0:
        stderr = await proc.stderr.read()
        raise RuntimeError(f"ffmpeg failed: returncode={proc.returncode}, err={stderr[:400]!r}")

    return str(output_path)


def extract_links_from_text(text: str) -> List[str]:
    """A minimal URL extractor. If your txt has one URL per line this works well."""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    urls = []
    for l in lines:
        if l.startswith("http://") or l.startswith("https://"):
            urls.append(l)
        else:
            # sometimes text contains raw links with spaces; try to find http
            if "http" in l:
                parts = l.split()
                for p in parts:
                    if p.startswith("http://") or p.startswith("https://"):
                        urls.append(p)
    return urls


# ---------- Queue and Worker (Mode B) ----------
class LinkProcessor:
    def __init__(self, app):
        self.app = app
        self.queue: asyncio.Queue = asyncio.Queue()
        self.workers: List[asyncio.Task] = []
        self.ffmpeg_sem = asyncio.Semaphore(MAX_CONCURRENT_FFMPEG)
        self.http_client = httpx.AsyncClient(timeout=HTTPX_TIMEOUT)
        self._last_status_time = 0

    async def start_workers(self):
        logger.info("Starting %d worker(s)", MAX_WORKERS)
        for _ in range(MAX_WORKERS):
            task = asyncio.create_task(self.worker_loop())
            self.workers.append(task)

    async def stop_workers(self):
        logger.info("Stopping workers, sending None sentinel(s)")
        for _ in range(len(self.workers)):
            await self.queue.put(None)
        await asyncio.gather(*self.workers)
        await self.http_client.aclose()

    async def enqueue_links(self, update: Update, links: List[str]):
        # Place metadata with each queue item
        for i, url in enumerate(links, 1):
            item = {"url": url, "chat_id": update.effective_chat.id, "message_id": update.message.message_id, "index": i, "total": len(links)}
            await self.queue.put(item)
        await self.safe_reply(update, f"✅ Enqueued {len(links)} links for background processing.")

    async def worker_loop(self):
        while True:
            item = await self.queue.get()
            if item is None:  # sentinel to stop
                self.queue.task_done()
                break

            url = item.get("url")
            chat_id = item.get("chat_id")
            index = item.get("index")
            total = item.get("total")

            try:
                # perform processing
                await self.process_single(chat_id, url, index, total)
            except Exception as e:
                logger.exception("Error processing %s: %s", url, e)
                # attempt to notify user
                try:
                    await self.app.bot.send_message(chat_id=chat_id, text=f"❗ Error processing {pathlib.Path(url).name}: {e}")
                except Exception:
                    logger.exception("Failed to send error message to user")
            finally:
                self.queue.task_done()

    async def process_single(self, chat_id: int, url: str, index: int, total: int):
        shortname = pathlib.Path(url).name
        # send a small status update occasionally
        now = asyncio.get_event_loop().time()
        if now - self._last_status_time > BATCH_MESSAGE_INTERVAL:
            await self.safe_send(chat_id, f"⏬ Processing {index}/{total}: {shortname}")
            self._last_status_time = now

        if url.endswith(".m3u8"):
            out_mp4 = str(DOWNLOADS_DIR / f"{index:04d}_{shortname.replace('.m3u8', '.mp4')}")
            # limit ffmpeg concurrency using semaphore
            async with self.ffmpeg_sem:
                try:
                    path = await convert_m3u8_async(url, out_mp4)
                except Exception as e:
                    raise
            # upload
            await self.upload_file(chat_id, path)
            # cleanup
            await self.safe_remove(path)

        else:
            out_file = str(DOWNLOADS_DIR / f"{index:04d}_{shortname}")
            try:
                path = await download_file_async(url, out_file, client=self.http_client)
            except Exception as e:
                raise
            await self.upload_file(chat_id, path)
            await self.safe_remove(path)

    async def upload_file(self, chat_id: int, path: str):
        # send file to user; use send_document which handles large uploads (under Telegram limits)
        try:
            # open file in binary mode (streaming)
            async with aiofiles.open(path, 'rb') as f:
                data = await f.read()
            await self.app.bot.send_document(chat_id=chat_id, document=data, filename=pathlib.Path(path).name)
        except Exception as e:
            logger.exception("Upload failed for %s", path)
            # fallback: try reading in normal blocking way (less ideal)
            try:
                with open(path, 'rb') as fh:
                    await self.app.bot.send_document(chat_id=chat_id, document=fh, filename=pathlib.Path(path).name)
            except Exception:
                logger.exception("Fallback upload also failed for %s", path)

    async def safe_remove(self, path: str):
        try:
            os.remove(path)
        except Exception:
            logger.exception("Could not remove %s", path)

    async def safe_reply(self, update: Update, text: str):
        try:
            await update.message.reply_text(text)
        except Exception:
            logger.exception("safe_reply failed")

    async def safe_send(self, chat_id: int, text: str):
        try:
            await self.app.bot.send_message(chat_id=chat_id, text=text)
        except Exception:
            logger.exception("safe_send failed")


# ---------- Telegram Handlers ----------
async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Hi! Send me a .txt with links (one per line) and I'll download them in background.")


async def txt_file_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming text file or message containing links."""
    logger.info("Received file/message from %s", update.effective_user.id)

    # get file content if it's a document
    text_content = None
    if update.message.document and update.message.document.mime_type in ("text/plain", "application/octet-stream"):
        # download the txt file to memory then decode
        file = await update.message.document.get_file()
        raw = await file.download_as_bytearray()
        try:
            text_content = raw.decode('utf-8')
        except UnicodeDecodeError:
            # try latin-1 as fallback
            text_content = raw.decode('latin-1')
    else:
        # if user directly sent a message with links
        if update.message.text:
            text_content = update.message.text

    if not text_content:
        await update.message.reply_text("No text content found in the message/document.")
        return

    links = extract_links_from_text(text_content)
    if not links:
        await update.message.reply_text("No valid links found in text.")
        return

    # enqueue links for background processing
    processor: LinkProcessor = context.bot_data.get('link_processor')
    if not processor:
        await update.message.reply_text("Server not ready: background processor missing.")
        return

    await processor.enqueue_links(update, links)


async def shutdown(app):
    logger.info("Shutdown requested")
    processor: LinkProcessor = app.bot_data.get('link_processor')
    if processor:
        await processor.stop_workers()


# ---------- Main application ----------
def main():
    if TELEGRAM_TOKEN == "YOUR_TOKEN_HERE":
        logger.error("Please set TELEGRAM_TOKEN environment variable before running.")
        return

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    processor = LinkProcessor(app)
    # store processor in bot_data for handlers to use
    app.bot_data['link_processor'] = processor

    # register handlers
    app.add_handler(MessageHandler(filters.COMMAND & filters.Regex('start'), start_handler))
    # for uploaded txt files or direct text messages
    app.add_handler(MessageHandler(filters.Document.ALL | filters.TEXT, txt_file_handler))

    # start worker tasks when app starts
    async def on_startup(app):
        logger.info("App startup: starting background workers")
        await processor.start_workers()

    async def on_shutdown(app):
        logger.info("App shutdown: stopping workers")
        await processor.stop_workers()

    app.post_init = on_startup

    # run
    logger.info("Starting Telegram bot application")
    app.run_polling()


if __name__ == '__main__':
    main()
