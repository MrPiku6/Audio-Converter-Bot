import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from pydub import AudioSegment
from pydub.effects import normalize
import subprocess

# FFmpeg path set karo
AudioSegment.converter = "/usr/bin/ffmpeg"
AudioSegment.ffmpeg = "/usr/bin/ffmpeg"
AudioSegment.ffprobe = "/usr/bin/ffprobe"

# Logging setup
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Bot Token
BOT_TOKEN = os.getenv("BOT_TOKEN", "8468003219:AAFrSJjcnZxBdLGfGiyF5CCCc7g2gNVxTVE")

# Temp folder
TEMP_DIR = "temp_audio"
os.makedirs(TEMP_DIR, exist_ok=True)

# Supported formats
AUDIO_FORMATS = {
    'mp3': 'MP3',
    'wav': 'WAV', 
    'ogg': 'OGG',
    'm4a': 'M4A',
    'flac': 'FLAC',
    'aac': 'AAC'
}

# Bitrate options
BITRATES = {
    '64': '64 kbps',
    '96': '96 kbps', 
    '128': '128 kbps',
    '192': '192 kbps',
    '256': '256 kbps',
    '320': '320 kbps'
}

# User sessions
user_sessions = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command handler"""
    welcome_msg = (
        "🎵 *Advanced Audio Converter Bot* 🎵\n\n"
        "Multiple features ke saath audio processing!\n\n"
        "*Features:*\n"
        "• Format Conversion (MP3, WAV, OGG, etc)\n"  
        "• Bitrate Selection (64-320 kbps)\n"
        "• Audio Trimming\n"
        "• Volume Normalization\n"
        "• Audio Compression\n\n"
        "*Usage:*\n"
        "1. Send audio file\n"
        "2. Choose feature\n"
        "3. Get converted file\n\n"
        "Commands:\n"
        "/start - Start bot\n"
        "/help - Help guide\n"
        "/formats - Supported formats"
    )
    await update.message.reply_text(welcome_msg, parse_mode='Markdown')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Help command handler"""
    help_text = (
        "🔧 *Audio Converter Bot Help*\n\n"
        "*Available Features:*\n"
        "🎵 Format Conversion\n"
        "⚡ Bitrate Control\n" 
        "✂️ Audio Trimming\n"
        "🔊 Volume Normalization\n"
        "📊 Audio Compression\n\n"
        "*How to use:*\n"
        "1. Send audio file (document or audio)\n"
        "2. Select desired feature\n"
        "3. Configure settings\n"
        "4. Download converted file\n\n"
        "*Limits:*\n"
        "• Max file size: 20MB\n"
        "• Max processing time: 2 minutes"
    )
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def formats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show supported formats"""
    formats_text = "🎵 *Supported Formats:*\n\n"
    for fmt, name in AUDIO_FORMATS.items():
        formats_text += f"• {name} (.{fmt})\n"
    
    formats_text += "\n⚡ *Available Bitrates:*\n"
    for br, desc in BITRATES.items():
        formats_text += f"• {desc}\n"
    
    await update.message.reply_text(formats_text, parse_mode='Markdown')

async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Audio file handler"""
    message = update.message
    user_id = message.from_user.id
    
    # Audio or document check
    if message.audio:
        file = message.audio
        file_name = file.file_name or "audio"
    elif message.document:
        file = message.document
        file_name = file.file_name
        if not file_name or not any(file_name.lower().endswith(f'.{fmt}') for fmt in AUDIO_FORMATS.keys()):
            await message.reply_text("❌ Please send a valid audio file.")
            return
    else:
        return
    
    # File size check
    if file.file_size > 20 * 1024 * 1024:
        await message.reply_text("❌ File too large! Maximum 20MB allowed.")
        return
    
    status_msg = await message.reply_text("⏳ Downloading audio file...")
    
    try:
        # Download file
        new_file = await context.bot.get_file(file.file_id)
        input_path = os.path.join(TEMP_DIR, f"{user_id}_{file.file_unique_id}_{file_name}")
        await new_file.download_to_drive(input_path)
        
        # Store file info
        user_sessions[user_id] = {
            'input_file': input_path,
            'original_name': file_name,
            'file_size': file.file_size
        }
        
        # Show main menu
        await show_main_menu(status_msg)
        
    except Exception as e:
        logger.error(f"Download error: {e}")
        await status_msg.edit_text(f"❌ Error: {str(e)}")
        if 'input_path' in locals() and os.path.exists(input_path):
            os.remove(input_path)

async def show_main_menu(message):
    """Show main feature menu"""
    keyboard = [
        [InlineKeyboardButton("🎵 Format Convert", callback_data="menu_convert")],
        [InlineKeyboardButton("⚡ Bitrate Change", callback_data="menu_bitrate")],
        [InlineKeyboardButton("✂️ Trim Audio", callback_data="menu_trim")],
        [InlineKeyboardButton("🔊 Normalize Volume", callback_data="menu_normalize")],
        [InlineKeyboardButton("📊 Compress Audio", callback_data="menu_compress")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await message.edit_text(
        "✅ File downloaded!\n\nChoose feature:",
        reply_markup=reply_markup
    )

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Callback handler"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
    data = query.data
    session = user_sessions.get(user_id)
    
    if not session or not os.path.exists(session['input_file']):
        await query.edit_message_text("❌ Session expired. Please send audio again.")
        return
    
    if data == "menu_convert":
        await show_format_selection(query)
    elif data == "menu_bitrate":
        await show_bitrate_selection(query)
    elif data == "menu_trim":
        await query.edit_message_text(
            "✂️ *Audio Trim*\n\nSend start and end times in seconds.\nExample: `10 30` - from 10s to 30s\nFormat: `start_time end_time`",
            parse_mode='Markdown'
        )
        user_sessions[user_id]['waiting_for_trim'] = True
    elif data.startswith("convert_"):
        await handle_format_conversion(query, data.replace("convert_", ""))
    elif data.startswith("bitrate_"):
        await handle_bitrate_conversion(query, data.replace("bitrate_", ""))
    elif data == "menu_normalize":
        await handle_normalize_audio(query)
    elif data == "menu_compress":
        await handle_compress_audio(query)
    elif data == "menu_back":
        await show_main_menu(query)

async def show_format_selection(query):
    """Show format selection"""
    keyboard = []
    row = []
    for fmt, name in AUDIO_FORMATS.items():
        row.append(InlineKeyboardButton(name, callback_data=f"convert_{fmt}"))
        if len(row) == 3:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="menu_back")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("🎯 Select output format:", reply_markup=reply_markup)

async def show_bitrate_selection(query):
    """Show bitrate selection"""
    keyboard = []
    row = []
    for br, desc in BITRATES.items():
        row.append(InlineKeyboardButton(desc, callback_data=f"bitrate_{br}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="menu_back")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("⚡ Select bitrate:", reply_markup=reply_markup)

async def handle_format_conversion(query, output_format):
    """Handle format conversion"""
    user_id = query.from_user.id
    session = user_sessions.get(user_id)
    
    await query.edit_message_text(f"🔄 Converting to {output_format.upper()}...")
    
    try:
        audio = AudioSegment.from_file(session['input_file'])
        base_name = os.path.splitext(session['original_name'])[0]
        output_file = os.path.join(TEMP_DIR, f"{user_id}_{base_name}_converted.{output_format}")
        
        audio.export(output_file, format=output_format, bitrate="192k")
        
        await query.message.reply_document(
            document=open(output_file, 'rb'),
            filename=f"{base_name}.{output_format}",
            caption=f"✅ Converted to {output_format.upper()}!"
        )
        
        await query.edit_message_text("✅ Conversion complete!")
        cleanup_files(session['input_file'], output_file)
        user_sessions.pop(user_id, None)
        
    except Exception as e:
        logger.error(f"Conversion error: {e}")
        await query.edit_message_text(f"❌ Conversion failed: {str(e)}")
        cleanup_files(session.get('input_file'))
        user_sessions.pop(user_id, None)

async def handle_bitrate_conversion(query, bitrate):
    """Handle bitrate conversion"""
    user_id = query.from_user.id
    session = user_sessions.get(user_id)
    
    await query.edit_message_text(f"⚡ Changing bitrate to {bitrate}kbps...")
    
    try:
        audio = AudioSegment.from_file(session['input_file'])
        original_ext = os.path.splitext(session['original_name'])[1][1:] or 'mp3'
        base_name = os.path.splitext(session['original_name'])[0]
        output_file = os.path.join(TEMP_DIR, f"{user_id}_{base_name}_{bitrate}kbps.{original_ext}")
        
        audio.export(output_file, format=original_ext, bitrate=f"{bitrate}k")
        
        await query.message.reply_document(
            document=open(output_file, 'rb'),
            filename=f"{base_name}_{bitrate}kbps.{original_ext}",
            caption=f"✅ Bitrate: {bitrate}kbps!"
        )
        
        await query.edit_message_text("✅ Bitrate change complete!")
        cleanup_files(session['input_file'], output_file)
        user_sessions.pop(user_id, None)
        
    except Exception as e:
        logger.error(f"Bitrate error: {e}")
        await query.edit_message_text(f"❌ Bitrate change failed: {str(e)}")
        cleanup_files(session.get('input_file'))
        user_sessions.pop(user_id, None)

async def handle_normalize_audio(query):
    """Handle volume normalization"""
    user_id = query.from_user.id
    session = user_sessions.get(user_id)
    
    await query.edit_message_text("🔊 Normalizing volume...")
    
    try:
        audio = AudioSegment.from_file(session['input_file'])
        normalized_audio = normalize(audio)
        
        base_name = os.path.splitext(session['original_name'])[0]
        output_file = os.path.join(TEMP_DIR, f"{user_id}_{base_name}_normalized.mp3")
        
        normalized_audio.export(output_file, format="mp3", bitrate="192k")
        
        await query.message.reply_document(
            document=open(output_file, 'rb'),
            filename=f"{base_name}_normalized.mp3",
            caption="✅ Volume normalized!"
        )
        
        await query.edit_message_text("✅ Normalization complete!")
        cleanup_files(session['input_file'], output_file)
        user_sessions.pop(user_id, None)
        
    except Exception as e:
        logger.error(f"Normalization error: {e}")
        await query.edit_message_text(f"❌ Normalization failed: {str(e)}")
        cleanup_files(session.get('input_file'))
        user_sessions.pop(user_id, None)

async def handle_compress_audio(query):
    """Handle audio compression"""
    user_id = query.from_user.id
    session = user_sessions.get(user_id)
    
    await query.edit_message_text("📊 Compressing audio...")
    
    try:
        audio = AudioSegment.from_file(session['input_file'])
        base_name = os.path.splitext(session['original_name'])[0]
        output_file = os.path.join(TEMP_DIR, f"{user_id}_{base_name}_compressed.mp3")
        
        audio.export(output_file, format="mp3", bitrate="128k")
        
        await query.message.reply_document(
            document=open(output_file, 'rb'),
            filename=f"{base_name}_compressed.mp3",
            caption="✅ Audio compressed!"
        )
        
        await query.edit_message_text("✅ Compression complete!")
        cleanup_files(session['input_file'], output_file)
        user_sessions.pop(user_id, None)
        
    except Exception as e:
        logger.error(f"Compression error: {e}")
        await query.edit_message_text(f"❌ Compression failed: {str(e)}")
        cleanup_files(session.get('input_file'))
        user_sessions.pop(user_id, None)

async def handle_trim_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle trim time input"""
    user_id = update.message.from_user.id
    session = user_sessions.get(user_id)
    
    if not session or not session.get('waiting_for_trim'):
        return
    
    try:
        times = update.message.text.split()
        if len(times) != 2:
            await update.message.reply_text("❌ Invalid format. Use: `start_time end_time`")
            return
        
        start_time = int(times[0]) * 1000
        end_time = int(times[1]) * 1000
        
        if start_time < 0 or end_time <= start_time:
            await update.message.reply_text("❌ Invalid times.")
            return
        
        await update.message.reply_text(f"✂️ Trimming from {times[0]}s to {times[1]}s...")
        
        audio = AudioSegment.from_file(session['input_file'])
        
        if end_time > len(audio):
            end_time = len(audio)
            await update.message.reply_text("⚠️ End time adjusted to audio length.")
        
        trimmed_audio = audio[start_time:end_time]
        base_name = os.path.splitext(session['original_name'])[0]
        output_file = os.path.join(TEMP_DIR, f"{user_id}_{base_name}_trimmed.mp3")
        
        trimmed_audio.export(output_file, format="mp3", bitrate="192k")
        
        await update.message.reply_document(
            document=open(output_file, 'rb'),
            filename=f"{base_name}_trimmed.mp3",
            caption=f"✅ Trimmed: {times[0]}s to {times[1]}s!"
        )
        
        cleanup_files(session['input_file'], output_file)
        user_sessions.pop(user_id, None)
        
    except ValueError:
        await update.message.reply_text("❌ Invalid numbers. Enter valid seconds.")
    except Exception as e:
        logger.error(f"Trim error: {e}")
        await update.message.reply_text(f"❌ Trimming failed: {str(e)}")
        cleanup_files(session.get('input_file'))
        user_sessions.pop(user_id, None)

def cleanup_files(*files):
    """Cleanup temporary files"""
    for file_path in files:
        try:
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
        except Exception as e:
            logger.error(f"Cleanup error {file_path}: {e}")

def main():
    """Main function"""
    try:
        subprocess.run([AudioSegment.ffmpeg, '-version'], check=True, capture_output=True)
        logger.info("FFmpeg configured successfully")
    except Exception as e:
        logger.error(f"FFmpeg error: {e}")
    
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("formats", formats_command))
    application.add_handler(MessageHandler(filters.AUDIO | filters.Document.AUDIO, handle_audio))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_trim_message))
    application.add_handler(CallbackQueryHandler(handle_callback, pattern="^menu_|^convert_|^bitrate_"))
    
    logger.info("Bot starting...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()