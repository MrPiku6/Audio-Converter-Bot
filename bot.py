import os
import logging
import asyncio
import subprocess
import time
import re
import requests
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

def self_ping():
    """Khud ko ping karega taaki bot sleep na kare"""
    while True:
        try:
            port = os.environ.get("PORT", 8080)
            # Render URL mil jaye to best hai, nahi to localhost
            render_url = os.environ.get("RENDER_EXTERNAL_URL") 
            if render_url:
                requests.get(render_url)
                logger.info(f"Pinged self at {render_url}")
            else:
                requests.get(f"http://127.0.0.1:{port}")
                logger.info("Pinged localhost")
        except Exception as e:
            logger.error(f"Ping Error: {e}")
        time.sleep(600) # Har 10 minute mein ping

def start_keep_alive():
    # Flask Server Thread
    t1 = Thread(target=run_flask)
    t1.daemon = True
    t1.start()
    
    # Self Ping Thread
    t2 = Thread(target=self_ping)
    t2.daemon = True
    t2.start()

# --- CONFIGURATION ---
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
# Force Sub Variable
FORCE_SUB_CHANNEL = os.getenv("@DARK_RIFT_ZONE") 

TEMP_DIR = "temp_audio"
os.makedirs(TEMP_DIR, exist_ok=True)

AUDIO_FORMATS = {'mp3': 'MP3', 'm4a': 'M4A', 'wav': 'WAV', 'ogg': 'OGG', 'flac': 'FLAC', 'aac': 'AAC'}
BITRATES = {'64': '64k', '128': '128k', '192': '192k', '256': '256k', '320': '320k'}

user_sessions = {}

# --- HELPER FUNCTIONS ---

async def check_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check if user is subscribed to the channel"""
    if not FORCE_SUB_CHANNEL or FORCE_SUB_CHANNEL.strip() == "":
        # Agar channel set nahi hai to allow karo
        return True
    
    user_id = update.effective_user.id
    chat_id = FORCE_SUB_CHANNEL if FORCE_SUB_CHANNEL.startswith("@") else f"@{FORCE_SUB_CHANNEL}"

    try:
        member = await context.bot.get_chat_member(chat_id=chat_id, user_id=user_id)
        if member.status in [ChatMember.LEFT, ChatMember.BANNED]:
            return False
        return True
    except Exception as e:
        logger.error(f"Force Sub Error: {e}")
        # IMPORTANT: Agar bot admin nahi hai to error aayega.
        # Agar aap chahte hain user bina join kiye use na kare, to return False karein.
        if "Chat not found" in str(e) or "bot is not a member" in str(e):
            await context.bot.send_message(chat_id=user_id, text="❌ **Error:** Bot channel ka Admin nahi hai.\nAdmin ko boliye mujhe channel me add karein aur Admin banayein.")
            return False
        return False # Strict Mode: Error aaya to bhi block karo

async def send_force_sub_message(update: Update):
    channel_name = FORCE_SUB_CHANNEL.replace('@', '')
    # Universal Link format
    join_link = f"https://t.me/{channel_name}"
    
    keyboard = [
        [InlineKeyboardButton("📢 Join Channel", url=join_link)],
        [InlineKeyboardButton("✅ I have Joined", callback_data="check_sub")]
    ]
    msg = f"🔒 *Access Denied!*\n\nBot use karne ke liye hamara channel join karein: @{channel_name}\nJoin karke 'I have Joined' par click karein."
    
    if update.message:
        await update.message.reply_text(msg, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))
    elif update.callback_query:
        # Try editing, if fails, send new
        try:
            await update.callback_query.edit_message_text(msg, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))
        except:
             await update.callback_query.message.reply_text(msg, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))

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
        "Main aapki audio files ko convert, edit aur compress kar sakta hoon!\n\n"
        "🚀 *Features:*\n"
        "• 📹 Video se Audio (MP3/M4A)\n"
        "• 📉 Smart Compression\n"
        "• 🎧 8D Audio Effect\n"
        "• 🔊 Bass Boost\n"
        "• ✂️ Easy Trimming\n\n"
        "👉 *Shuru karne ke liye mujhe koi File bhejein!*"
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
    
    if file_obj.file_size > 100 * 1024 * 1024: 
        await message.reply_text("❌ File too large! Max 100MB allowed.")
        return

    status_msg = await message.reply_text("⏳ Downloading media...")
    
    try:
        new_file = await context.bot.get_file(file_obj.file_id)
        unique_id = f"{user_id}_{int(time.time())}"
        
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
        try:
            await message.edit_text(text, parse_mode='Markdown', reply_markup=reply_markup)
        except:
            await message.reply_text(text, parse_mode='Markdown', reply_markup=reply_markup)
    else:
        await message.reply_text(text, parse_mode='Markdown', reply_markup=reply_markup)

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    
    # Special handler for check_sub to avoid answering prematurely
    if query.data == "check_sub":
        is_sub = await check_subscription(update, context)
        if is_sub:
            await query.answer("✅ Verified! File bhejein.")
            await query.edit_message_text("✅ *Verified!*\n\nAb aap bot use kar sakte hain. Koi bhi Audio/Video file bhejein!", parse_mode='Markdown')
        else:
            await query.answer("❌ Aapne abhi tak channel join nahi kiya!", show_alert=True)
        return

    await query.answer()
    user_id = query.from_user.id
    data = query.data
    
    if user_id not in user_sessions:
        await query.edit_message_text("❌ Session expired. Please upload file again.")
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
        session['format'] = 'aac' 
        session['bitrate'] = '64'
        session['normalize'] = True 
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
            "👇 *Start aur End time seconds mein likhein.*\n"
            "Example:\n"
            "• `0 30` (Pehle 30 second)\n"
            "• `60 120` (1 min se 2 min tak)\n"
            "• `0 0` (Cancel/Reset)"
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
    
    await query.edit_message_text("⚙️ Processing... Please wait!")
    
    try:
        output_path, thumb_path, caption = await asyncio.to_thread(run_ffmpeg_command, session)
        
        if thumb_path and os.path.exists(thumb_path):
            await query.message.reply_audio(
                audio=open(output_path, 'rb'), 
                caption=caption, 
                thumbnail=open(thumb_path, 'rb'), 
                title=os.path.splitext(session['original_name'])[0], 
                performer="ConvertedByBot"
            )
        else:
            await query.message.reply_document(
                document=open(output_path, 'rb'), 
                caption=caption
            )
            
        await query.edit_message_text("✅ Conversion Successful!")
        
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
    
    if session['is_video']:
        thumb_name = f"thumb_{unique_id}.jpg"
        thumb_path = os.path.join(TEMP_DIR, thumb_name)
        extracted = extract_thumbnail(input_path, thumb_path)
        if not extracted: thumb_path = None
    
    cmd = ["ffmpeg", "-i", input_path]
    
    if session['trim_start'] > 0:
        cmd.extend(["-ss", str(session['trim_start'])])
    if session['trim_end']:
        cmd.extend(["-to", str(session['trim_end'])])
        
    af_chain = []
    if session['speed'] != 1.0: af_chain.append(f"atempo={session['speed']}")
    if session['bass_boost']: af_chain.append("bass=g=10:f=100:w=0.5")
    if session['8d_audio']: af_chain.append("apulsator=hz=0.125")
    if session['normalize']: af_chain.append("dynaudnorm=f=150:g=15")
        
    if af_chain: cmd.extend(["-filter:a", ",".join(af_chain)])
    cmd.extend(["-b:a", f"{session['bitrate']}k"])
    
    if session['is_video']:
        cmd.append("-vn")
    else:
        cmd.extend(["-map", "0:a", "-map", "0:v?", "-c:v", "copy", "-id3v2_version", "3"])

    cmd.extend(["-y", output_path])
    
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    
    if result.returncode != 0:
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
        cleaned = re.sub(r'[^\d\s]', ' ', text)
        parts = cleaned.split()
        
        try:
            if len(parts) == 2:
                start, end = int(parts[0]), int(parts[1])
                if start == 0 and end == 0:
                    user_sessions[user_id]['trim_start'] = 0
                    user_sessions[user_id]['trim_end'] = None
                    await update.message.reply_text("🔄 Trim Cancelled (Full Audio).")
                elif start >= end and end != 0:
                     await update.message.reply_text("❌ Start time chota hona chahiye End time se.")
                     return
                else:
                    user_sessions[user_id]['trim_start'] = start
                    user_sessions[user_id]['trim_end'] = end
                    await update.message.reply_text(f"✅ Trim Set: {start}s to {end}s")
            else:
                raise ValueError("Not enough numbers")
                
            user_sessions[user_id]['waiting_for_trim'] = False
            await show_main_menu(update.message)
            
        except ValueError:
            await update.message.reply_text("❌ Invalid format.\nDo number bhejein jaise: `10 30`")

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
