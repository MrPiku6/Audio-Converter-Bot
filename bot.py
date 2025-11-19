import os
import logging
import asyncio
import subprocess
import time
import re
from threading import Thread
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from telegram.error import BadRequest

# --- FLASK KEEP-ALIVE SERVER ---
app = Flask('')

@app.route('/')
def home():
    return "Bot is Online! 🚀"

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

# 👇 Yaha apna Token aur Channel Username daalein
BOT_TOKEN = "8468003219:AAFrSJjcnZxBdLGfGiyF5CCCc7g2gNVxTVE"  
FORCE_CHANNEL = "@DARK_RIFT_ZONE" # Example: "@MyTechChannel" (Bot must be Admin there)

TEMP_DIR = "temp_audio"
os.makedirs(TEMP_DIR, exist_ok=True)

# Supported formats
AUDIO_FORMATS = {'mp3': 'MP3', 'm4a': 'M4A', 'wav': 'WAV', 'flac': 'FLAC', 'ogg': 'OGG'}
BITRATES = {'64': '64k', '128': '128k', '192': '192k', '256': '256k', '320': '320k'}

# User sessions
user_sessions = {}

# --- HELPER FUNCTIONS ---
async def check_subscription(user_id, context):
    """Check if user joined the channel"""
    if not FORCE_CHANNEL or FORCE_CHANNEL == "@YourChannelUsername":
        return True # Agar channel set nahi hai to skip karo
    
    try:
        member = await context.bot.get_chat_member(chat_id=FORCE_CHANNEL, user_id=user_id)
        if member.status in ['left', 'kicked']:
            return False
        return True
    except BadRequest:
        logger.error("Bot channel me admin nahi hai ya channel ID galat hai.")
        return True # Error aaye to user ko block mat karo, allow kar do
    except Exception as e:
        logger.error(f"Check Sub Error: {e}")
        return True

def get_duration(file_path):
    try:
        cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", file_path]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return float(result.stdout.strip())
    except:
        return 0.0

def extract_thumbnail(video_path, output_thumb):
    try:
        cmd = ["ffmpeg", "-i", video_path, "-ss", "00:00:01", "-vframes", "1", output_thumb, "-y"]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return output_thumb
    except:
        return None

# --- BOT HANDLERS ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # Force Sub Check
    is_member = await check_subscription(user_id, context)
    if not is_member:
        keyboard = [[InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{FORCE_CHANNEL.replace('@', '')}")],
                    [InlineKeyboardButton("✅ Check Joined", callback_data="check_joined")]]
        await update.message.reply_text(f"🔒 **Access Denied!**\n\nPlease join our channel {FORCE_CHANNEL} to use this bot.", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        return

    welcome_msg = (
        "👋 *Welcome to Audio Master Bot!* \n\n"
        "I can convert, compress, trim, and boost your audio files while keeping metadata intact!\n\n"
        "🔥 *Features:*\n"
        "• 📹 Video to Audio (with Thumbnail)\n"
        "• 🏷️ Keeps Cover Art & Metadata\n"
        "• 📉 Smart Compression\n"
        "• ✂️ Easy Trimming\n"
        "• 🔊 Bass Boost & 8D Effect\n\n"
        "📤 **Send any Audio or Video file to start!**"
    )
    await update.message.reply_text(welcome_msg, parse_mode='Markdown')

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    user_id = message.from_user.id
    
    # Force Sub Check
    if not await check_subscription(user_id, context):
        await start(update, context)
        return

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
        if file_name.lower().endswith(('.mp4', '.mkv', '.avi', '.webm')):
            is_video = True
        elif not any(file_name.lower().endswith(f'.{fmt}') for fmt in AUDIO_FORMATS.keys()):
            await message.reply_text("❌ Format not supported.")
            return
    else:
        return
    
    if file_obj.file_size > 50 * 1024 * 1024: 
        await message.reply_text("❌ File too large! (Max 50MB)")
        return

    status_msg = await message.reply_text("📥 **Downloading...**", parse_mode='Markdown')
    
    try:
        new_file = await context.bot.get_file(file_obj.file_id)
        unique_id = f"{user_id}_{int(time.time())}"
        input_path = os.path.join(TEMP_DIR, f"{unique_id}_in_{file_name}")
        await new_file.download_to_drive(input_path)
        
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
            'compress': False,
            'speed': 1.0,
            'is_video': is_video,
            'waiting_for_trim': False
        }
        
        await show_main_menu(status_msg)
        
    except Exception as e:
        logger.error(f"Download Error: {e}")
        await status_msg.edit_text("❌ Failed to download.")

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
    
    settings_text = (
        f"• Format: `{session['format'].upper()}`\n"
        f"• Bitrate: `{session['bitrate']}kbps`\n"
        f"• Speed: `{session['speed']}x`\n"
    )
    
    if session.get('trim_start') > 0 or session.get('trim_end'):
        end_t = session['trim_end'] if session['trim_end'] else int(dur)
        settings_text += f"• Trim: `{session['trim_start']}s - {end_t}s`\n"
        
    if session.get('bass_boost'): settings_text += "• Bass Boost: `ON`\n"
    if session.get('compress'): settings_text += "• Mode: `Compress`\n"

    text = (
        f"{type_text} *Control Panel*\n"
        f"📂 `{session['original_name']}`\n"
        f"⏱ `{int(dur)} sec`\n\n"
        f"⚙️ *Current Settings:*\n{settings_text}"
    )

    keyboard = [
        [InlineKeyboardButton("🎵 Format", callback_data="menu_format"),
         InlineKeyboardButton("⚡ Bitrate", callback_data="menu_bitrate")],
        [InlineKeyboardButton("✂️ Trim", callback_data="menu_trim"),
         InlineKeyboardButton("📉 Compress", callback_data="toggle_compress")],
        [InlineKeyboardButton("⏩ Speed", callback_data="menu_speed"),
         InlineKeyboardButton("🔊 Bass Boost", callback_data="toggle_bass")],
        [InlineKeyboardButton("🚀 START PROCESSING", callback_data="process_start")]
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
    
    # Check Sub for buttons too
    if data == "check_joined":
        if await check_subscription(user_id, context):
            await query.edit_message_text("✅ Verified! You can now use the bot. Send /start again.")
        else:
            await query.answer("❌ You haven't joined yet!", show_alert=True)
        return

    if user_id not in user_sessions:
        await query.edit_message_text("❌ Session expired.")
        return

    session = user_sessions[user_id]

    if data == "toggle_compress":
        session['compress'] = not session['compress']
        if session['compress']:
            session['bitrate'] = '64' # Auto set low bitrate
            session['format'] = 'mp3'
        else:
            session['bitrate'] = '192'
        await show_main_menu(query.message)
    elif data == "toggle_bass":
        session['bass_boost'] = not session['bass_boost']
        await show_main_menu(query.message)
    elif data == "menu_format":
        buttons = [[InlineKeyboardButton(v, callback_data=f"set_fmt_{k}") for k, v in list(AUDIO_FORMATS.items())[i:i+3]] for i in range(0, len(AUDIO_FORMATS), 3)]
        buttons.append([InlineKeyboardButton("🔙 Back", callback_data="back_main")])
        await query.edit_message_text("Select Format:", reply_markup=InlineKeyboardMarkup(buttons))
    elif data == "menu_bitrate":
        buttons = [[InlineKeyboardButton(v, callback_data=f"set_bit_{k}") for k, v in list(BITRATES.items())[i:i+3]] for i in range(0, len(BITRATES), 3)]
        buttons.append([InlineKeyboardButton("🔙 Back", callback_data="back_main")])
        await query.edit_message_text("Select Quality:", reply_markup=InlineKeyboardMarkup(buttons))
    elif data == "menu_speed":
        speeds = [0.5, 0.8, 1.0, 1.25, 1.5, 2.0]
        buttons = [[InlineKeyboardButton(f"{s}x", callback_data=f"set_spd_{s}") for s in speeds]]
        buttons.append([InlineKeyboardButton("🔙 Back", callback_data="back_main")])
        await query.edit_message_text("Select Speed:", reply_markup=InlineKeyboardMarkup(buttons))
    elif data == "menu_trim":
        session['waiting_for_trim'] = True
        dur = int(session.get('duration', 0))
        msg = (
            f"✂️ *Trim Mode*\n"
            f"Total Duration: `{dur}s`\n\n"
            "Send the **Start** and **End** time in seconds.\n"
            "Examples:\n"
            "• `10 60` (Cut from 10s to 60s)\n"
            "• `30 0` (Cut from 30s to end)\n"
            "• `0 0` (Cancel Trim)"
        )
        await query.edit_message_text(msg, parse_mode='Markdown')
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
    
    await query.edit_message_text("⚡ Processing your file... Please wait.")
    
    try:
        output_path, thumb_path, caption = await asyncio.to_thread(run_ffmpeg_command, session)
        
        if thumb_path and os.path.exists(thumb_path):
            # Use thumbnail if available (Video -> Audio)
            await query.message.reply_audio(
                audio=open(output_path, 'rb'), 
                caption=caption, 
                thumbnail=open(thumb_path, 'rb'), 
                title=os.path.splitext(session['original_name'])[0],
                performer="Converted by UltraBot"
            )
        else:
            # Send as document/audio but preserve original thumb if it was in metadata
            try:
                await query.message.reply_audio(
                    audio=open(output_path, 'rb'), 
                    caption=caption,
                    title=os.path.splitext(session['original_name'])[0]
                )
            except:
                # Fallback to document if audio fails
                await query.message.reply_document(document=open(output_path, 'rb'), caption=caption)
            
        await query.edit_message_text("✅ Completed!")
        
        cleanup_files(output_path, thumb_path, session['input_file'])
        del user_sessions[user_id]
        
    except Exception as e:
        logger.error(f"Processing Error: {e}")
        await query.edit_message_text("❌ An error occurred during processing.")
        cleanup_files(session.get('input_file'))

def run_ffmpeg_command(session):
    input_path = session['input_file']
    unique_id = session['unique_id']
    out_fmt = session['format']
    output_filename = f"processed_{unique_id}.{out_fmt}"
    output_path = os.path.join(TEMP_DIR, output_filename)
    thumb_path = None
    
    cmd = ["ffmpeg", "-i", input_path]
    
    # Trim
    if session['trim_start'] > 0:
        cmd.extend(["-ss", str(session['trim_start'])])
    if session['trim_end']:
        cmd.extend(["-to", str(session['trim_end'])])
        
    # Filters (Bass, Speed, Normalize)
    af_filters = []
    if session['speed'] != 1.0:
        af_filters.append(f"atempo={session['speed']}")
    if session['bass_boost']:
        af_filters.append("bass=g=10:f=100,equalizer=f=40:t=h:w=50:g=5")
    if session['normalize']:
        af_filters.append("loudnorm")
        
    if af_filters:
        cmd.extend(["-af", ",".join(af_filters)])
        
    # Bitrate & Encoding
    cmd.extend(["-b:a", f"{session['bitrate']}k"])
    
    # METADATA & COVER ART PRESERVATION LOGIC
    # Map audio stream
    cmd.extend(["-map", "0:a:0"])
    
    # If input is audio, try to copy video stream (which is cover art in MP3/FLAC)
    if not session['is_video']:
        cmd.extend(["-map", "0:v:0?"]) # ? means optional (if cover exists)
        cmd.extend(["-c:v", "copy"])   # Don't re-encode the image
        cmd.extend(["-id3v2_version", "3"]) # Better compatibility for MP3 tags
        cmd.extend(["-map_metadata", "0"]) # Copy global metadata
    else:
        # If video, extract thumbnail separately for Telegram upload
        thumb_name = f"thumb_{unique_id}.jpg"
        thumb_path = os.path.join(TEMP_DIR, thumb_name)
        extract_thumbnail(input_path, thumb_path)
        if not os.path.exists(thumb_path): thumb_path = None

    # Output
    cmd.extend(["-y", output_path])
    
    # Run
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    
    caption = (
        f"✅ *Processed Successfully*\n"
        f"🎶 Format: {out_fmt.upper()}\n"
        f"📊 Bitrate: {session['bitrate']}k\n"
    )
    if session['compress']: caption += "📉 Compressed: Yes"
    
    return output_path, thumb_path, caption

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id in user_sessions and user_sessions[user_id].get('waiting_for_trim'):
        text = update.message.text
        
        # Robust parsing logic
        # Replace comma, hyphens with space to handle "10-60" or "10,60"
        clean_text = re.sub(r'[^0-9\s]', ' ', text)
        parts = clean_text.split()
        
        if len(parts) >= 2:
            try:
                start = int(parts[0])
                end = int(parts[1])
                
                if start == 0 and end == 0:
                    user_sessions[user_id]['trim_start'] = 0
                    user_sessions[user_id]['trim_end'] = None
                    await update.message.reply_text("✅ Trim Cancelled.")
                else:
                    if start < 0: start = 0
                    # Validate against duration
                    dur = user_sessions[user_id].get('duration', 0)
                    if end > dur and dur > 0: end = int(dur)
                    
                    user_sessions[user_id]['trim_start'] = start
                    user_sessions[user_id]['trim_end'] = end if end > start else None
                    await update.message.reply_text(f"✅ Trim Set: {start}s to {end if end else 'End'}s")
                
                user_sessions[user_id]['waiting_for_trim'] = False
                await show_main_menu(update.message)
                return
            except ValueError:
                pass
        
        await update.message.reply_text("❌ Invalid Format. Please send seconds like `10 60` or `0 0` to cancel.")

def cleanup_files(*files):
    for f in files:
        try:
            if f and os.path.exists(f): os.remove(f)
        except Exception: pass

def main():
    if BOT_TOKEN == "8468003219:AAFrSJjcnZxBdLGfGiyF5CCCc7g2gNVxTVE":
        print("❌ ERROR: Please put your bot token in bot.py file!")
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
