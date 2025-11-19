import os
import logging
import asyncio
import subprocess
from threading import Thread
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from pydub import AudioSegment
from pydub.effects import normalize, speedup

# --- FLASK KEEP-ALIVE SERVER ---
app = Flask('')

@app.route('/')
def home():
    return "Bot is Running! 🚀"

def run_flask():
    # Render PORT environment variable provide karta hai
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def start_keep_alive():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()

# --- CONFIGURATION ---
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Bot Token
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Temp folder
TEMP_DIR = "temp_audio"
os.makedirs(TEMP_DIR, exist_ok=True)

# FFmpeg setup (Docker/Linux ke liye auto-detect)
AudioSegment.converter = "ffmpeg" 
AudioSegment.ffmpeg = "ffmpeg"
AudioSegment.ffprobe = "ffprobe"

# Supported formats
AUDIO_FORMATS = {'mp3': 'MP3', 'wav': 'WAV', 'ogg': 'OGG', 'm4a': 'M4A', 'flac': 'FLAC', 'aac': 'AAC'}
BITRATES = {'64': '64k', '128': '128k', '192': '192k', '256': '256k', '320': '320k'}

# User sessions
user_sessions = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_msg = (
        "🎵 *Ultra Audio Converter Bot* 🎵\n\n"
        "I can convert, trim, boost bass, change speed, and extract audio from video!\n\n"
        "*Features:*\n"
        "• 📹 Video to Audio\n"
        "• 🔄 Format Conversion\n"
        "• 🔊 Bass Boost & Normalize\n"
        "• ⏩ Speed Change\n"
        "• 📉 Compression\n"
        "• ✂️ Trimming\n"
        "• 🔉 Fade In/Out\n\n"
        "Just send an **Audio** or **Video** file to start!"
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
    
    # Size check (Telegram Bot API limit ~50MB)
    if file_obj.file_size > 49 * 1024 * 1024: 
        await message.reply_text("❌ File too large! Max 50MB allowed by Bot API.")
        return

    status_msg = await message.reply_text("⏳ Downloading media...")
    
    try:
        new_file = await context.bot.get_file(file_obj.file_id)
        input_path = os.path.join(TEMP_DIR, f"{user_id}_{file_obj.file_unique_id}_{file_name}")
        await new_file.download_to_drive(input_path)
        
        user_sessions[user_id] = {
            'input_file': input_path,
            'original_name': file_name,
            'format': 'mp3',
            'bitrate': '192',
            'trim_start': 0, 'trim_end': None,
            'normalize': False, 'compress': False,
            'bass_boost': False, 'speed': 1.0,
            'fade': False,
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
    
    text = (
        f"{type_text} *Processing Menu*\n"
        "Configure settings:\n\n"
        f"• Format: `{session.get('format', 'mp3').upper()}`\n"
        f"• Bitrate: `{session.get('bitrate', '192')}kbps`\n"
        f"• Speed: `{session.get('speed', 1.0)}x`\n"
        f"• Bass Boost: `{'✅' if session.get('bass_boost') else '❌'}`\n"
        f"• Fade In/Out: `{'✅' if session.get('fade') else '❌'}`\n"
        f"• Normalize: `{'✅' if session.get('normalize') else '❌'}`\n"
        f"• Compress: `{'✅' if session.get('compress') else '❌'}`\n"
    )
    
    if session.get('trim_start') > 0 or session.get('trim_end'):
        end_t = session.get('trim_end') if session.get('trim_end') else "End"
        text += f"• Trim: `{session.get('trim_start')}s - {end_t}s`\n"

    keyboard = [
        [InlineKeyboardButton("🎵 Format", callback_data="menu_format"),
         InlineKeyboardButton("⚡ Bitrate", callback_data="menu_bitrate")],
        [InlineKeyboardButton("⏩ Speed", callback_data="menu_speed"),
         InlineKeyboardButton("🔊 Bass Boost", callback_data="toggle_bass")],
        [InlineKeyboardButton("🔉 Fade In/Out", callback_data="toggle_fade"),
         InlineKeyboardButton("📊 Compress", callback_data="toggle_compress")],
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
        await query.edit_message_text("❌ Session expired. Please upload again.")
        return

    session = user_sessions[user_id]

    if data == "toggle_normalize":
        session['normalize'] = not session['normalize']
        await show_main_menu(query.message)
    elif data == "toggle_compress":
        session['compress'] = not session['compress']
        session['bitrate'] = '64' if session['compress'] else '192'
        await show_main_menu(query.message)
    elif data == "toggle_bass":
        session['bass_boost'] = not session['bass_boost']
        await show_main_menu(query.message)
    elif data == "toggle_fade":
        session['fade'] = not session['fade']
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
        speeds = [0.75, 1.0, 1.25, 1.5, 2.0]
        buttons = [[InlineKeyboardButton(f"{s}x", callback_data=f"set_spd_{s}") for s in speeds]]
        buttons.append([InlineKeyboardButton("🔙 Back", callback_data="back_main")])
        await query.edit_message_text("Select Playback Speed:", reply_markup=InlineKeyboardMarkup(buttons))
    elif data == "menu_trim":
        session['waiting_for_trim'] = True
        await query.edit_message_text("✂️ *Trim Mode*\nSend start and end seconds (e.g., `10 60`).\nSend `0 0` to cancel.", parse_mode='Markdown')
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
    
    await query.edit_message_text("⚙️ Processing... This may take a moment.")
    
    try:
        output_path, caption = await asyncio.to_thread(process_audio_logic, session)
        
        await query.message.reply_document(document=open(output_path, 'rb'), caption=caption)
        await query.edit_message_text("✅ Done!")
        
        cleanup_files(output_path, session['input_file'])
        del user_sessions[user_id]
        
    except Exception as e:
        logger.error(f"Processing Error: {e}")
        await query.edit_message_text(f"❌ Error: {str(e)}")
        cleanup_files(session.get('input_file'))

def process_audio_logic(session):
    input_path = session['input_file']
    fmt = session['format']
    audio = AudioSegment.from_file(input_path)
    
    if session['trim_start'] > 0 or session['trim_end']:
        start = session['trim_start'] * 1000
        end = session['trim_end'] * 1000 if session['trim_end'] else len(audio)
        audio = audio[start:end]

    if session['speed'] != 1.0:
        audio = speedup(audio, playback_speed=session['speed'])

    if session['bass_boost']:
        bass_line = audio.low_pass_filter(120).apply_gain(6)
        audio = audio.overlay(bass_line)

    if session['normalize']:
        audio = normalize(audio)

    if session['fade']:
        audio = audio.fade_in(2000).fade_out(2000)

    bitrate = f"{session['bitrate']}k"
    output_filename = f"processed_{os.path.splitext(session['original_name'])[0]}.{fmt}"
    output_path = os.path.join(TEMP_DIR, output_filename)
    
    audio.export(output_path, format=fmt, bitrate=bitrate)
    
    caption = f"✅ *Completed*\nFormat: {fmt.upper()} | Bitrate: {bitrate}\nSpeed: {session['speed']}x"
    return output_path, caption

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id in user_sessions and user_sessions[user_id].get('waiting_for_trim'):
        try:
            parts = update.message.text.split()
            start, end = int(parts[0]), int(parts[1])
            user_sessions[user_id]['trim_start'] = start
            user_sessions[user_id]['trim_end'] = end if end > 0 else None
            user_sessions[user_id]['waiting_for_trim'] = False
            await update.message.reply_text("✅ Trim Set!")
            await show_main_menu(update.message)
        except:
            await update.message.reply_text("❌ Invalid. Use `0 0` or `10 60`.")

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