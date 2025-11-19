import os
import logging
import asyncio
import subprocess
import time
import re
from threading import Thread
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatMember
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
FORCE_SUB_CHANNEL = os.getenv("DARK_RIFT_ZONE") # Example: "@mychannel"

TEMP_DIR = "temp_audio"
os.makedirs(TEMP_DIR, exist_ok=True)

# Supported formats
AUDIO_FORMATS = {'mp3': 'MP3', 'm4a': 'M4A', 'wav': 'WAV', 'ogg': 'OGG', 'flac': 'FLAC', 'aac': 'AAC'}
BITRATES = {'64': '64k', '128': '128k', '192': '192k', '256': '256k', '320': '320k'}

# User sessions store
user_sessions = {}

# --- HELPER FUNCTIONS ---

async def check_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check if user is subscribed to the channel"""
    if not FORCE_SUB_CHANNEL:
        return True
    
    user_id = update.effective_user.id
    try:
        member = await context.bot.get_chat_member(chat_id=FORCE_SUB_CHANNEL, user_id=user_id)
        if member.status in [ChatMember.LEFT, ChatMember.BANNED]:
            return False
        return True
    except Exception as e:
        logger.error(f"Channel check error: {e}")
        # If bot isn't admin or channel invalid, allow user to proceed to avoid blocking
        return True

async def send_force_sub_message(update: Update):
    """Send message to join channel"""
    keyboard = [
        [InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{FORCE_SUB_CHANNEL.replace('@', '')}")],
        [InlineKeyboardButton("✅ I have Joined", callback_data="check_sub")]
    ]
    msg = f"🔒 *Locked!*\n\nYou must join our channel {FORCE_SUB_CHANNEL} to use this bot."
    if update.message:
        await update.message.reply_text(msg, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))
    elif update.callback_query:
        await update.callback_query.edit_message_text(msg, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))

def get_duration(file_path):
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
    if not await check_subscription(update, context):
        await send_force_sub_message(update)
        return

    welcome_msg = (
        "🎵 *Ultimate Audio Studio* 🎵\n\n"
        "I can convert, edit, and optimize your audio files while keeping your covers/metadata intact!\n\n"
        "🚀 *Features:*\n"
        "• 📹 Video to Audio (MP3/M4A)\n"
        "• 📉 Smart Compression\n"
        "• 🎧 8D Audio Effect\n"
        "• 🔊 Bass Boost & Normalize\n"
        "• ✂️ Easy Trimming\n"
        "• 🖼️ Preserves Album Art\n\n"
        "👉 *Send me a File to start!*"
    )
    await update.message.reply_text(welcome_msg, parse_mode='Markdown')

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_subscription(update, context):
        await send_force_sub_message(update)
        return

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
        if file_name.lower().endswith(('.mp4', '.mkv', '.avi', '.webm')):
            is_video = True
        elif not any(file_name.lower().endswith(f'.{fmt}') for fmt in AUDIO_FORMATS.keys()):
            await message.reply_text("❌ Unsupported file format.")
            return
    else:
        return
    
    if file_obj.file_size > 100 * 1024 * 1024: # 100MB Limit
        await message.reply_text("❌ File too large! Max 100MB allowed.")
        return

    status_msg = await message.reply_text("⏳ Downloading media...")
    
    try:
        new_file = await context.bot.get_file(file_obj.file_id)
        unique_id = f"{user_id}_{int(time.time())}"
        
        # Preserve extension for FFmpeg type detection
        ext = os.path.splitext(file_name)[1]
        input_path = os.path.join(TEMP_DIR, f"{unique_id}_input{ext}")
        
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
            '8d_audio': False,
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
        text = "❌ Session expired. Upload again."
        if hasattr(message, 'edit_text'): await message.edit_text(text)
        else: await message.reply_text(text)
        return

    type_text = "📹 Video" if session.get('is_video') else "🎵 Audio"
    dur = session.get('duration', 0)
    
    # Determine indicators
    bass_icon = '✅' if session.get('bass_boost') else '❌'
    norm_icon = '✅' if session.get('normalize') else '❌'
    eightd_icon = '✅' if session.get('8d_audio') else '❌'
    
    text = (
        f"{type_text} *Control Panel*\n"
        f"File: `{session.get('original_name')}`\n"
        f"Length: `{int(dur)}s`\n\n"
        "⚙️ *Current Settings:*\n"
        f"• Format: `{session.get('format', 'mp3').upper()}` | {session.get('bitrate')}kbps\n"
        f"• Effects: Bass: {bass_icon} | Norm: {norm_icon} | 8D: {eightd_icon}\n"
        f"• Speed: `{session.get('speed', 1.0)}x`\n"
    )
    
    if session.get('trim_start') > 0 or session.get('trim_end'):
        end_t = session.get('trim_end') if session.get('trim_end') else int(dur)
        text += f"• ✂️ Trim: `{session.get('trim_start')}s` to `{end_t}s`\n"

    keyboard = [
        [InlineKeyboardButton("📉 Compress (Auto)", callback_data="set_compress"),
         InlineKeyboardButton("🎵 Format", callback_data="menu_format")],
        
        [InlineKeyboardButton("🔊 Bass Boost", callback_data="toggle_bass"),
         InlineKeyboardButton("🎧 8D Audio", callback_data="toggle_8d")],
        
        [InlineKeyboardButton("✂️ Trim", callback_data="menu_trim"),
         InlineKeyboardButton("📢 Normalize", callback_data="toggle_normalize")],
         
        [InlineKeyboardButton("⏩ Speed", callback_data="menu_speed"),
         InlineKeyboardButton("⚡ Bitrate", callback_data="menu_bitrate")],
         
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
    
    if data == "check_sub":
        if await check_subscription(update, context):
            await query.edit_message_text("✅ Verified! You can now use the bot.")
        else:
            await query.answer("❌ You haven't joined yet!", show_alert=True)
        return

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
    elif data == "toggle_8d":
        session['8d_audio'] = not session['8d_audio']
        await show_main_menu(query.message)
        
    elif data == "set_compress":
        # Preset for compression
        session['format'] = 'aac' # Efficient format
        session['bitrate'] = '64'
        session['normalize'] = True # Good for compressed audio
        await query.answer("✅ Compression Preset Applied!", show_alert=True)
        await show_main_menu(query.message)
        
    elif data == "menu_format":
        buttons = [[InlineKeyboardButton(v, callback_data=f"set_fmt_{k}") for k, v in list(AUDIO_FORMATS.items())[i:i+3]] for i in range(0, len(AUDIO_FORMATS), 3)]
        buttons.append([InlineKeyboardButton("🔙 Back", callback_data="back_main")])
        await query.edit_message_text("Select Output Format:", reply_markup=InlineKeyboardMarkup(buttons))
        
    elif data == "menu_bitrate":
        buttons = [[InlineKeyboardButton(v, callback_data=f"set_bit_{k}") for k, v in list(BITRATES.items())[i:i+3]] for i in range(0, len(BITRATES), 3)]
        buttons.append([InlineKeyboardButton("🔙 Back", callback_data="back_main")])
        await query.edit_message_text("Select Quality (Bitrate):", reply_markup=InlineKeyboardMarkup(buttons))
        
    elif data == "menu_speed":
        speeds = [0.5, 0.8, 1.0, 1.25, 1.5, 2.0]
        buttons = [[InlineKeyboardButton(f"{s}x", callback_data=f"set_spd_{s}") for s in speeds]]
        buttons.append([InlineKeyboardButton("🔙 Back", callback_data="back_main")])
        await query.edit_message_text("Select Playback Speed:", reply_markup=InlineKeyboardMarkup(buttons))
        
    elif data == "menu_trim":
        session['waiting_for_trim'] = True
        dur = int(session.get('duration', 0))
        msg = (
            f"✂️ *Trim Mode*\n"
            f"Total Duration: {dur} seconds.\n\n"
            "👇 *Type the Start and End time in seconds.*\n"
            "Examples:\n"
            "• `0 30` (First 30 seconds)\n"
            "• `60 120` (From 1 min to 2 mins)\n"
            "• `0 0` (Cancel/Reset Trim)"
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
    
    await query.edit_message_text("⚙️ Cooking your audio... Please wait!")
    
    try:
        output_path, thumb_path, caption = await asyncio.to_thread(run_ffmpeg_command, session)
        
        # Sending file
        if thumb_path and os.path.exists(thumb_path):
            await query.message.reply_audio(
                audio=open(output_path, 'rb'), 
                caption=caption, 
                thumbnail=open(thumb_path, 'rb'), 
                title=os.path.splitext(session['original_name'])[0], 
                performer="ConvertedByBot"
            )
        else:
            # If it's audio but no thumb, send as audio
            await query.message.reply_document(
                document=open(output_path, 'rb'), 
                caption=caption
            )
            
        await query.edit_message_text("✅ Conversion Successful!")
        
        # Cleanup
        cleanup_files(output_path, thumb_path, session['input_file'])
        del user_sessions[user_id]
        
    except Exception as e:
        logger.error(f"Processing Error: {e}")
        await query.edit_message_text(f"❌ Error happened: {str(e)}")
        cleanup_files(session.get('input_file'))

def run_ffmpeg_command(session):
    input_path = session['input_file']
    unique_id = session['unique_id']
    out_fmt = session['format']
    output_filename = f"processed_{unique_id}.{out_fmt}"
    output_path = os.path.join(TEMP_DIR, output_filename)
    thumb_path = None
    
    # Extract thumbnail for Video inputs (or try for audio)
    if session['is_video']:
        thumb_name = f"thumb_{unique_id}.jpg"
        thumb_path = os.path.join(TEMP_DIR, thumb_name)
        extracted = extract_thumbnail(input_path, thumb_path)
        if not extracted: thumb_path = None
    
    # Build Command
    # We use -y to overwrite
    cmd = ["ffmpeg", "-i", input_path]
    
    # Trimming
    if session['trim_start'] > 0:
        cmd.extend(["-ss", str(session['trim_start'])])
    if session['trim_end']:
        cmd.extend(["-to", str(session['trim_end'])])
        
    # Audio Filters
    af_chain = []
    
    if session['speed'] != 1.0:
        af_chain.append(f"atempo={session['speed']}")
        
    if session['bass_boost']:
        # High shelf bass boost
        af_chain.append("bass=g=10:f=100:w=0.5")
        
    if session['8d_audio']:
        # Pan circling effect (apulsator)
        af_chain.append("apulsator=hz=0.125")
        
    if session['normalize']:
        af_chain.append("dynaudnorm=f=150:g=15")
        
    if af_chain:
        cmd.extend(["-filter:a", ",".join(af_chain)])
        
    # Bitrate
    cmd.extend(["-b:a", f"{session['bitrate']}k"])
    
    # Metadata handling
    # If input is Audio, we want to COPY the video stream (cover art) if format supports it
    # If input is Video, we strip video (-vn)
    if session['is_video']:
        cmd.append("-vn")
    else:
        # Try to map all streams (audio + cover art)
        # -c:v copy keeps the image data as is
        # -map 0 ensures metadata is carried over
        cmd.extend(["-map", "0:a", "-map", "0:v?", "-c:v", "copy", "-id3v2_version", "3"])

    # Output
    cmd.extend(["-y", output_path])
    
    logger.info(f"FFmpeg Command: {' '.join(cmd)}")
    
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    
    if result.returncode != 0:
        # Fallback: Sometimes map 0:v fails if no cover exists or format mismatch
        # Retry without cover art mapping
        logger.warning("FFmpeg failed with metadata mapping, retrying simple conversion...")
        simple_cmd = ["ffmpeg", "-i", input_path, "-vn"]
        if session['trim_start'] > 0: simple_cmd.extend(["-ss", str(session['trim_start'])])
        if session['trim_end']: simple_cmd.extend(["-to", str(session['trim_end'])])
        if af_chain: simple_cmd.extend(["-filter:a", ",".join(af_chain)])
        simple_cmd.extend(["-b:a", f"{session['bitrate']}k", "-y", output_path])
        
        subprocess.run(simple_cmd, check=True)

    caption = (
        f"✅ *Processed Successfully* \n"
        f"📁 Format: {out_fmt.upper()}\n"
        f"📉 Size Optimized: {'Yes' if session['bitrate']=='64' else 'No'}"
    )
    
    return output_path, thumb_path, caption

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id in user_sessions and user_sessions[user_id].get('waiting_for_trim'):
        text = update.message.text.strip()
        
        # Improved parsing for "10 60" or "10,60" or "10-60"
        # Removes non-digit chars except space
        cleaned = re.sub(r'[^\d\s]', ' ', text)
        parts = cleaned.split()
        
        try:
            if len(parts) == 2:
                start, end = int(parts[0]), int(parts[1])
                if start == 0 and end == 0:
                    # Reset
                    user_sessions[user_id]['trim_start'] = 0
                    user_sessions[user_id]['trim_end'] = None
                    await update.message.reply_text("🔄 Trim cancelled (Full audio selected).")
                elif start >= end and end != 0:
                     await update.message.reply_text("❌ Error: Start time must be less than End time.")
                     return
                else:
                    user_sessions[user_id]['trim_start'] = start
                    user_sessions[user_id]['trim_end'] = end
                    await update.message.reply_text(f"✅ Trim set: {start}s to {end}s")
            else:
                raise ValueError("Not enough numbers")
                
            user_sessions[user_id]['waiting_for_trim'] = False
            await show_main_menu(update.message)
            
        except ValueError:
            await update.message.reply_text("❌ Invalid format.\nSend two numbers like: `10 30`\n(Start at 10s, End at 30s)")

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
