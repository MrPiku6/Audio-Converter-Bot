import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from pydub import AudioSegment
from pydub.effects import normalize
import subprocess

# FFmpeg configuration
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

# User sessions for multi-step processing
user_sessions = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command handler"""
    welcome_msg = (
        "🎵 *Advanced Audio Converter Bot* 🎵\n\n"
        "Process audio files with multiple features simultaneously!\n\n"
        "*Available Features:*\n"
        "• Format Conversion (MP3, WAV, OGG, M4A, FLAC, AAC)\n"  
        "• Bitrate Selection (64-320 kbps)\n"
        "• Audio Trimming (Cut specific parts)\n"
        "• Volume Normalization\n"
        "• Audio Compression\n\n"
        "*How to use:*\n"
        "1. Send an audio file - menu will open automatically\n"
        "2. Configure all settings\n"
        "3. Get your processed file\n\n"
        "*Quick Commands (after sending audio):*\n"
        "/convert - Change format only\n"
        "/bitrate - Change bitrate only\n"
        "/trim - Trim audio only\n"
        "/settings - Full configuration\n\n"
        "Just send an audio file to start!"
    )
    await update.message.reply_text(welcome_msg, parse_mode='Markdown')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Help command handler"""
    help_text = (
        "🔧 *Advanced Audio Processor Help*\n\n"
        "*You can combine multiple features:*\n"
        "• Convert format AND change bitrate\n"
        "• Trim AND normalize volume\n"
        "• Compress AND change format\n"
        "• Any combination you want!\n\n"
        "*Simple Process:*\n"
        "1. Send audio file (menu opens automatically)\n"
        "2. Choose your settings\n"
        "3. Click PROCESS NOW\n"
        "4. Download processed file\n\n"
        "*Quick Commands:*\n"
        "After sending audio, use:\n"
        "/convert - Quick format change\n"
        "/bitrate - Quick bitrate change\n"
        "/trim - Quick trim setup\n"
        "/settings - Full settings\n\n"
        "*Limits:*\n"
        "• Max file size: 20MB\n"
        "• Supported: MP3, WAV, OGG, M4A, FLAC, AAC"
    )
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Settings command to configure processing"""
    user_id = update.message.from_user.id
    
    # Check if user has uploaded a file
    if user_id not in user_sessions or 'input_file' not in user_sessions[user_id]:
        await update.message.reply_text(
            "❌ Please send an audio file first, then use /settings to configure processing."
        )
        return
    
    await show_main_menu(update.message)

async def quick_convert(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Quick format conversion"""
    user_id = update.message.from_user.id
    if user_id not in user_sessions or 'input_file' not in user_sessions[user_id]:
        await update.message.reply_text("❌ Please send an audio file first.")
        return
    
    # Set default settings for quick convert
    user_sessions[user_id].update({
        'bitrate': '192',
        'trim_start': 0,
        'trim_end': None,
        'normalize': False,
        'compress': False
    })
    
    await show_format_selection(update.message)

async def quick_bitrate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Quick bitrate change"""
    user_id = update.message.from_user.id
    if user_id not in user_sessions or 'input_file' not in user_sessions[user_id]:
        await update.message.reply_text("❌ Please send an audio file first.")
        return
    
    # Set default settings for quick bitrate change
    user_sessions[user_id].update({
        'format': 'mp3',
        'trim_start': 0,
        'trim_end': None,
        'normalize': False,
        'compress': False
    })
    
    await show_bitrate_selection(update.message)

async def quick_trim(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Quick trim setup"""
    user_id = update.message.from_user.id
    if user_id not in user_sessions or 'input_file' not in user_sessions[user_id]:
        await update.message.reply_text("❌ Please send an audio file first.")
        return
    
    # Set default settings for quick trim
    user_sessions[user_id].update({
        'format': 'mp3',
        'bitrate': '192',
        'normalize': False,
        'compress': False
    })
    
    await update.message.reply_text(
        "✂️ *Quick Trim Setup*\n\n"
        "Send start and end times in seconds:\n"
        "Format: `start_time end_time`\n\n"
        "*Examples:*\n"
        "• `0 60` - First 60 seconds\n"
        "• `30 90` - From 30s to 90s\n"
        "• `0 0` - No trimming\n\n"
        "Enter times now:",
        parse_mode='Markdown'
    )
    user_sessions[user_id]['waiting_for_trim'] = True

async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Audio file handler - AUTO MENU SHOWS HERE"""
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
            await message.reply_text("❌ Please send a valid audio file (MP3, WAV, OGG, M4A, FLAC, AAC).")
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
        
        # Initialize user session with default settings
        user_sessions[user_id] = {
            'input_file': input_path,
            'original_name': file_name,
            'file_size': file.file_size,
            'format': 'mp3',  # Default format
            'bitrate': '192',  # Default bitrate
            'trim_start': 0,
            'trim_end': None,  # None means end of file
            'normalize': False,
            'compress': False
        }
        
        # AUTO SHOW MENU AFTER DOWNLOAD
        await show_main_menu(status_msg)
        
    except Exception as e:
        logger.error(f"Download error: {e}")
        await status_msg.edit_text(f"❌ Error: {str(e)}")
        if 'input_path' in locals() and os.path.exists(input_path):
            os.remove(input_path)

async def show_main_menu(message):
    """Show main processing menu - AUTO CALLED AFTER AUDIO UPLOAD"""
    keyboard = [
        [InlineKeyboardButton("🎵 Output Format", callback_data="set_format")],
        [InlineKeyboardButton("⚡ Bitrate", callback_data="set_bitrate")],
        [InlineKeyboardButton("✂️ Trim Audio", callback_data="set_trim")],
        [InlineKeyboardButton("🔊 Normalization", callback_data="toggle_normalize")],
        [InlineKeyboardButton("📊 Compression", callback_data="toggle_compress")],
        [InlineKeyboardButton("🚀 PROCESS NOW", callback_data="process_now")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    user_id = message.from_user.id
    session = user_sessions.get(user_id, {})
    
    # Get current settings display
    trim_display = f"{session.get('trim_start', 0)}s - {session.get('trim_end', 'End')}s" if session.get('trim_start', 0) > 0 or session.get('trim_end') else "No trim"
    
    settings_text = (
        "🎵 *Audio Processing Menu*\n\n"
        "*Current Settings:*\n"
        f"• Format: `{session.get('format', 'mp3').upper()}`\n"
        f"• Bitrate: `{session.get('bitrate', '192')}kbps`\n"
        f"• Trim: `{trim_display}`\n"
        f"• Normalize: `{'✅ ON' if session.get('normalize', False) else '❌ OFF'}`\n"
        f"• Compress: `{'✅ ON' if session.get('compress', False) else '❌ OFF'}`\n\n"
        "Configure each setting, then click **PROCESS NOW**!\n\n"
        "*Quick commands:* /convert, /bitrate, /trim"
    )
    
    if hasattr(message, 'edit_text'):
        await message.edit_text(settings_text, parse_mode='Markdown', reply_markup=reply_markup)
    else:
        await message.reply_text(settings_text, parse_mode='Markdown', reply_markup=reply_markup)

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Main callback handler"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
    data = query.data
    session = user_sessions.get(user_id)
    
    if not session or not os.path.exists(session['input_file']):
        await query.edit_message_text("❌ Session expired. Please send audio file again.")
        return
    
    if data == "set_format":
        await show_format_selection(query)
    elif data == "set_bitrate":
        await show_bitrate_selection(query)
    elif data == "set_trim":
        await query.edit_message_text(
            "✂️ *Trim Settings*\n\n"
            "Send start and end times in seconds.\n\n"
            "*Examples:*\n"
            "• `0 60` - First 60 seconds\n"
            "• `30 90` - From 30s to 90s\n"
            "• `0 0` - No trimming (full audio)\n\n"
            "Format: `start_time end_time`\n\n"
            "Enter times now:",
            parse_mode='Markdown'
        )
        user_sessions[user_id]['waiting_for_trim'] = True
    elif data.startswith("format_"):
        selected_format = data.replace("format_", "")
        user_sessions[user_id]['format'] = selected_format
        await query.edit_message_text(f"✅ Output format set to: {selected_format.upper()}")
        await show_main_menu(query.message)
    elif data.startswith("bitrate_"):
        selected_bitrate = data.replace("bitrate_", "")
        user_sessions[user_id]['bitrate'] = selected_bitrate
        await query.edit_message_text(f"✅ Bitrate set to: {selected_bitrate}kbps")
        await show_main_menu(query.message)
    elif data == "toggle_normalize":
        current = user_sessions[user_id].get('normalize', False)
        user_sessions[user_id]['normalize'] = not current
        status = "ON" if not current else "OFF"
        await query.edit_message_text(f"✅ Volume normalization: {status}")
        await show_main_menu(query.message)
    elif data == "toggle_compress":
        current = user_sessions[user_id].get('compress', False)
        user_sessions[user_id]['compress'] = not current
        status = "ON" if not current else "OFF"
        await query.edit_message_text(f"✅ Compression: {status}")
        await show_main_menu(query.message)
    elif data == "process_now":
        await process_audio(query)
    elif data == "back_to_menu":
        await show_main_menu(query.message)

async def show_format_selection(message):
    """Show format selection"""
    keyboard = []
    row = []
    for fmt, name in AUDIO_FORMATS.items():
        row.append(InlineKeyboardButton(name, callback_data=f"format_{fmt}"))
        if len(row) == 3:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("🔙 Back to Menu", callback_data="back_to_menu")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if hasattr(message, 'edit_message_text'):
        await message.edit_message_text("🎯 Select output format:", reply_markup=reply_markup)
    else:
        await message.reply_text("🎯 Select output format:", reply_markup=reply_markup)

async def show_bitrate_selection(message):
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
    keyboard.append([InlineKeyboardButton("🔙 Back to Menu", callback_data="back_to_menu")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if hasattr(message, 'edit_message_text'):
        await message.edit_message_text("⚡ Select bitrate:", reply_markup=reply_markup)
    else:
        await message.reply_text("⚡ Select bitrate:", reply_markup=reply_markup)

async def process_audio(query):
    """Process audio with all selected settings"""
    user_id = query.from_user.id
    session = user_sessions.get(user_id)
    
    await query.edit_message_text("🔄 Processing audio with your settings...")
    
    try:
        # Load original audio
        audio = AudioSegment.from_file(session['input_file'])
        
        # Apply trimming if specified
        trim_start = session.get('trim_start', 0) * 1000  # Convert to milliseconds
        trim_end = session.get('trim_end')
        
        if trim_end:
            trim_end = trim_end * 1000  # Convert to milliseconds
            if trim_end > len(audio):
                trim_end = len(audio)
            audio = audio[trim_start:trim_end]
        elif trim_start > 0:
            audio = audio[trim_start:]
        
        # Apply normalization if enabled
        if session.get('normalize'):
            audio = normalize(audio)
        
        # Determine output format and bitrate
        output_format = session.get('format', 'mp3')
        
        # Adjust bitrate for compression - FIXED BITRATE ISSUE
        if session.get('compress'):
            # For compression, use lower bitrate but respect user's choice if it's already low
            current_bitrate = int(session.get('bitrate', '192'))
            if current_bitrate > 128:
                bitrate = "128k"
            else:
                bitrate = f"{current_bitrate}k"
        else:
            # Use user's selected bitrate
            bitrate = f"{session.get('bitrate', '192')}k"
        
        # Create output filename
        base_name = os.path.splitext(session['original_name'])[0]
        features = []
        
        if session.get('trim_start', 0) > 0 or session.get('trim_end'):
            features.append("trimmed")
        if session.get('normalize'):
            features.append("normalized")
        if session.get('compress'):
            features.append("compressed")
        
        if features:
            feature_suffix = "_" + "_".join(features)
        else:
            feature_suffix = "_processed"
        
        output_file = os.path.join(TEMP_DIR, f"{user_id}_{base_name}{feature_suffix}.{output_format}")
        
        # Export with selected settings - BITRATE NOW WORKS PROPERLY
        audio.export(output_file, format=output_format, bitrate=bitrate)
        
        # Prepare caption with processing details
        caption = (
            f"✅ Audio Processing Complete!\n\n"
            f"• Format: {output_format.upper()}\n"
            f"• Bitrate: {bitrate}\n"
        )
        
        if session.get('trim_start', 0) > 0 or session.get('trim_end'):
            trim_end_display = session['trim_end'] if session['trim_end'] else 'End'
            caption += f"• Trim: {session['trim_start']}s - {trim_end_display}s\n"
        if session.get('normalize'):
            caption += "• Volume: Normalized\n"
        if session.get('compress'):
            caption += "• Compression: Applied\n"
        
        # Send processed file
        await query.message.reply_document(
            document=open(output_file, 'rb'),
            filename=f"{base_name}{feature_suffix}.{output_format}",
            caption=caption
        )
        
        await query.edit_message_text("✅ Processing complete! File sent.")
        
        # Cleanup
        cleanup_files(session['input_file'], output_file)
        user_sessions.pop(user_id, None)
        
    except Exception as e:
        logger.error(f"Processing error: {e}")
        await query.edit_message_text(f"❌ Processing failed: {str(e)}")
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
        
        start_time = int(times[0])
        end_time = int(times[1])
        
        if start_time < 0 or (end_time != 0 and end_time <= start_time):
            await update.message.reply_text("❌ Invalid times. End time should be greater than start time.")
            return
        
        # Store trim settings
        user_sessions[user_id]['trim_start'] = start_time
        user_sessions[user_id]['trim_end'] = end_time if end_time > 0 else None
        user_sessions[user_id]['waiting_for_trim'] = False
        
        if end_time == 0:
            await update.message.reply_text("✅ Trim disabled (full audio will be used)")
        else:
            await update.message.reply_text(f"✅ Trim set: {start_time}s to {end_time}s")
        
        await show_main_menu(update.message)
        
    except ValueError:
        await update.message.reply_text("❌ Invalid numbers. Please enter valid seconds.")
    except Exception as e:
        logger.error(f"Trim settings error: {e}")
        await update.message.reply_text(f"❌ Error: {str(e)}")

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
    # Check FFmpeg
    try:
        subprocess.run([AudioSegment.ffmpeg, '-version'], check=True, capture_output=True)
        logger.info("FFmpeg configured successfully")
    except Exception as e:
        logger.error(f"FFmpeg error: {e}")
    
    # Create application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("settings", settings_command))
    application.add_handler(CommandHandler("convert", quick_convert))
    application.add_handler(CommandHandler("bitrate", quick_bitrate))
    application.add_handler(CommandHandler("trim", quick_trim))
    application.add_handler(MessageHandler(filters.AUDIO | filters.Document.AUDIO, handle_audio))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_trim_message))
    application.add_handler(CallbackQueryHandler(handle_callback, pattern="^.*$"))
    
    logger.info("Bot starting...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
