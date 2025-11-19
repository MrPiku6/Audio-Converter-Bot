import os
import logging
import asyncio
import subprocess
import time
from threading import Thread
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# --- FLASK KEEP-ALIVE SERVER ---
app = Flask('')

@app.route('/')
def home():
    return "Bot is Running! 🚀"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def start_keep_alive():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()

# --- CONFIGURATION ---
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
TEMP_DIR = "temp_audio"
os.makedirs(TEMP_DIR, exist_ok=True)

# Supported formats
AUDIO_FORMATS = {'mp3': 'MP3', 'wav': 'WAV', 'ogg': 'OGG', 'm4a': 'M4A', 'flac': 'FLAC', 'aac': 'AAC'}
BITRATES = {'64': '64k', '128': '128k', '192': '192k', '256': '256k', '320': '320k'}

# User sessions store
user_sessions = {}

# --- HELPER FUNCTIONS ---
def get_duration(file_path):
    """Get duration of file in seconds using ffprobe"""
    try:
        cmd = [
            "ffprobe", "-v", "error", "-show_entries", 
            "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", file_path
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return float(result.stdout.strip())
    except:
        return 0.0

def extract_thumbnail(video_path, output_thumb):
    """Extract a thumbnail from video"""
    try:
        cmd = [
            "ffmpeg", "-i", video_path, "-ss", "00:00:01", 
            "-vframes", "1", output_thumb, "-y"
        ]
        subprocess.run(cmd, check=True)
        return output_thumb
    except:
        return None

# --- BOT HANDLERS ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_msg = (
        "🎵 *Ultra Audio Converter v2.0* 🎵\n\n"
        "🚀 *Features Updated:*\n"
        "• 📹 Video to Audio (with Thumbnail)\n"
        "• 🔄 Fast Format Conversion\n"
        "• 🔊 Bass Boost (Dynamic)\n"
        "• ⏩ Speed Change (0.5x - 2.0x)\n"
        "• ✂️ Accurate Trimming\n"
        "• 📢 Volume Normalization\n\n"
        "👉 Send an **Audio** or **Video** file to begin!"
    )
    await update.message.reply_text(welcome_msg, parse_mode='Markdown')

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    user_id = message.from_user.id
    
    file_obj = None
    is_video = False
    file_name = "unknown"
    
    if message.audio:
        file_obj = message.audio
        file_name = file_obj.file_name or "audio.mp3"
    elif message.video:
        file_obj = message.video
        file_name = file_obj.file_name or "video.mp4"
        is_video = True
    elif message.document:
        file_obj = message.document
        file_name = file_obj.file_name
        if not file_name: return
        if file_name.lower().endswith(('.mp4', '.mkv', '.avi', '.mov', '.webm')):
            is_video = True
        elif not any(file_name.lower().endswith(f'.{fmt}') for fmt in AUDIO_FORMATS.keys()):
            await message.reply_text("❌ Unsupported file format.")
            return
    else:
        return
    
    # Limit 50MB
    if file_obj.file_size > 50 * 1024 * 1024: 
        await message.reply_text("❌ File too large! Max 50MB allowed.")
        return

    status_msg = await message.reply_text("⏳ Downloading media...")
    
    try:
        new_file = await context.bot.get_file(file_obj.file_id)
        unique_id = f"{user_id}_{int(time.time())}"
        input_path = os.path.join(TEMP_DIR, f"{unique_id}_input_{file_name}")
        await new_file.download_to_drive(input_path)
        
        # Calculate duration
        duration = get_duration(input_path)

        user_sessions[user_id] = {
            'input_file': input_path,
            'unique_id': unique_id,
            'original_name': file_name,
            'duration': duration,
            'format': 'mp3',
            'bitrate': '192',
            'trim_start': 0, 
            'trim_end': None,
            'normalize': False, 
            'bass_boost': False, 
            'speed': 1.0,
            'is_video': is_video,
            'waiting_for_trim': False
        }
        
        await show_main_menu(status_msg)
        
    except Exception as e:
        logger.error(f"Download Error: {e}")
        await status_msg.edit_text("❌ Download failed.")

async def show_main_menu(message):
    user_id = message.chat.id if hasattr(message, 'chat') else message.from_user.id
    session = user_sessions.get(user_id, {})
    
    if not session:
        text = "❌ Session expired. Please upload again."
        if hasattr(message, 'edit_text'): await message.edit_text(text)
        else: await message.reply_text(text)
        return

    type_text = "📹 Video" if session.get('is_video') else "🎵 Audio"
    dur = session.get('duration', 0)
    
    text = (
        f"{type_text} *Processing Menu*\n"
        f"File: `{session.get('original_name')}`\n"
        f"Duration: `{int(dur)} sec`\n\n"
        "⚙️ *Settings:*\n"
        f"• Format: `{session.get('format', 'mp3').upper()}`\n"
        f"• Bitrate: `{session.get('bitrate', '192')}kbps`\n"
        f"• Speed: `{session.get('speed', 1.0)}x`\n"
        f"• Bass Boost: `{'✅' if session.get('bass_boost') else '❌'}`\n"
        f"• Normalize: `{'✅' if session.get('normalize') else '❌'}`\n"
    )
    
    if session.get('trim_start') > 0 or session.get('trim_end'):
        end_t = session.get('trim_end') if session.get('trim_end') else int(dur)
        text += f"• Trim: `{session.get('trim_start')}s - {end_t}s`\n"

    keyboard = [
        [InlineKeyboardButton("🎵 Format", callback_data="menu_format"),
         InlineKeyboardButton("⚡ Bitrate", callback_data="menu_bitrate")],
        [InlineKeyboardButton("⏩ Speed", callback_data="menu_speed"),
         InlineKeyboardButton("🔊 Bass Boost", callback_data="toggle_bass")],
        [InlineKeyboardButton("✂️ Trim", callback_data="menu_trim"),
         InlineKeyboardButton("📢 Normalize", callback_data="toggle_normalize")],
        [InlineKeyboardButton("🚀 PROCESS NOW", callback_data="process_start")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if hasattr(message, 'edit_text'):
        await message.edit_text(text, parse_mode='Markdown', reply_markup=reply_markup)
    else:
        await message.reply_text(text, parse_mode='Markdown', reply_markup=reply_markup)

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data
    
    if user_id not in user_sessions:
        await query.edit_message_text("❌ Session expired.")
        return

    session = user_sessions[user_id]

    if data == "toggle_normalize":
        session['normalize'] = not session['normalize']
        await show_main_menu(query.message)
    elif data == "toggle_bass":
        session['bass_boost'] = not session['bass_boost']
        await show_main_menu(query.message)
    elif data == "menu_format":
        buttons = [[InlineKeyboardButton(v, callback_data=f"set_fmt_{k}") for k, v in list(AUDIO_FORMATS.items())[i:i+3]] for i in range(0, len(AUDIO_FORMATS), 3)]
        buttons.append([InlineKeyboardButton("🔙 Back", callback_data="back_main")])
        await query.edit_message_text("Select Output Format:", reply_markup=InlineKeyboardMarkup(buttons))
    elif data == "menu_bitrate":
        buttons = [[InlineKeyboardButton(v, callback_data=f"set_bit_{k}") for k, v in list(BITRATES.items())[i:i+3]] for i in range(0, len(BITRATES), 3)]
        buttons.append([InlineKeyboardButton("🔙 Back", callback_data="back_main")])
        await query.edit_message_text("Select Bitrate:", reply_markup=InlineKeyboardMarkup(buttons))
    elif data == "menu_speed":
        speeds = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0]
        buttons = [[InlineKeyboardButton(f"{s}x", callback_data=f"set_spd_{s}") for s in speeds]]
        buttons.append([InlineKeyboardButton("🔙 Back", callback_data="back_main")])
        await query.edit_message_text("Select Speed:", reply_markup=InlineKeyboardMarkup(buttons))
    elif data == "menu_trim":
        session['waiting_for_trim'] = True
        dur = int(session.get('duration', 0))
        await query.edit_message_text(f"✂️ *Trim Mode*\nFile Duration: {dur}s\n\nSend start and end seconds (e.g., `10 30`)\nSend `0 0` to cancel.", parse_mode='Markdown')
    elif data.startswith("set_fmt_"):
        session['format'] = data.split("_")[2]
        await show_main_menu(query.message)
    elif data.startswith("set_bit_"):
        session['bitrate'] = data.split("_")[2]
        await show_main_menu(query.message)
    elif data.startswith("set_spd_"):
        session['speed'] = float(data.split("_")[2])
        await show_main_menu(query.message)
    elif data == "back_main":
        session['waiting_for_trim'] = False
        await show_main_menu(query.message)
    elif data == "process_start":
        await process_audio_thread(query, context)

async def process_audio_thread(query, context):
    user_id = query.from_user.id
    session = user_sessions.get(user_id)
    
    await query.edit_message_text("⚙️ Processing with FFmpeg... (Fast Mode)")
    
    try:
        output_path, thumb_path, caption = await asyncio.to_thread(run_ffmpeg_command, session)
        
        if thumb_path and os.path.exists(thumb_path):
            await query.message.reply_audio(audio=open(output_path, 'rb'), caption=caption, thumbnail=open(thumb_path, 'rb'), title="Converted Audio", performer="UltraBot")
        else:
            await query.message.reply_document(document=open(output_path, 'rb'), caption=caption)
            
        await query.edit_message_text("✅ Task Completed!")
        
        # Cleanup
        cleanup_files(output_path, thumb_path, session['input_file'])
        del user_sessions[user_id]
        
    except Exception as e:
        logger.error(f"Processing Error: {e}")
        await query.edit_message_text(f"❌ Error: {str(e)}")
        cleanup_files(session.get('input_file'))

def run_ffmpeg_command(session):
    input_path = session['input_file']
    unique_id = session['unique_id']
    out_fmt = session['format']
    output_filename = f"processed_{unique_id}.{out_fmt}"
    output_path = os.path.join(TEMP_DIR, output_filename)
    thumb_path = None
    
    # Command Construction
    cmd = ["ffmpeg", "-i", input_path]
    
    # Trimming
    if session['trim_start'] > 0:
        cmd.extend(["-ss", str(session['trim_start'])])
    if session['trim_end']:
        cmd.extend(["-to", str(session['trim_end'])])
        
    # Audio Filters
    filters = []
    if session['speed'] != 1.0:
        filters.append(f"atempo={session['speed']}")
    if session['bass_boost']:
        # Strong bass boost: Gain 10dB at 100Hz
        filters.append("bass=g=10:f=100")
    if session['normalize']:
        filters.append("dynaudnorm")
        
    if filters:
        cmd.extend(["-filter:a", ",".join(filters)])
        
    # Bitrate
    cmd.extend(["-b:a", f"{session['bitrate']}k"])
    
    # Force format and overwrite
    cmd.extend(["-vn", "-y", output_path]) # -vn removes video stream
    
    # Extract thumbnail if video
    if session['is_video']:
        thumb_name = f"thumb_{unique_id}.jpg"
        thumb_path = os.path.join(TEMP_DIR, thumb_name)
        extracted = extract_thumbnail(input_path, thumb_path)
        if not extracted: thumb_path = None

    # Run Command
    logger.info(f"Running FFmpeg: {' '.join(cmd)}")
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    
    if result.returncode != 0:
        raise Exception(f"FFmpeg failed: {result.stderr}")
        
    caption = (
        f"✅ *Done!* \n"
        f"🎵 Format: {out_fmt.upper()}\n"
        f"⚡ Bitrate: {session['bitrate']}kbps\n"
        f"⏩ Speed: {session['speed']}x"
    )
    
    return output_path, thumb_path, caption

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id in user_sessions and user_sessions[user_id].get('waiting_for_trim'):
        try:
            text = update.message.text
            if text == "0 0":
                user_sessions[user_id]['trim_start'] = 0
                user_sessions[user_id]['trim_end'] = None
            else:
                parts = text.split()
                start, end = int(parts[0]), int(parts[1])
                user_sessions[user_id]['trim_start'] = start
                user_sessions[user_id]['trim_end'] = end if end > 0 else None
            
            user_sessions[user_id]['waiting_for_trim'] = False
            await update.message.reply_text("✅ Trim settings updated!")
            await show_main_menu(update.message)
        except:
            await update.message.reply_text("❌ Invalid format. Send start and end seconds like `10 60`.")

def cleanup_files(*files):
    for f in files:
        try:
            if f and os.path.exists(f): os.remove(f)
        except Exception: pass

def main():
    if not BOT_TOKEN:
        print("Please set BOT_TOKEN env variable!")
        return
    start_keep_alive()
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.AUDIO | filters.VIDEO | filters.Document.ALL, handle_file))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    application.add_handler(CallbackQueryHandler(handle_callback))
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()