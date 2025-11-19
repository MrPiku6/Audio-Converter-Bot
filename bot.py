import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from pydub import AudioSegment
from pydub.effects import normalize
import subprocess
import tempfile
from datetime import timedelta

# FFmpeg path set karo - Render par yeh path hota hai
AudioSegment.converter = "/usr/bin/ffmpeg"
AudioSegment.ffmpeg = "/usr/bin/ffmpeg"
AudioSegment.ffprobe = "/usr/bin/ffprobe"

# Logging setup
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Bot Token - Environment variable se lenge
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
        "🎵 *Audio Converter Bot me aapka swagat hai!* 🎵\n\n"
        "Main audio files ko convert kar sakta hu with advanced features.\n\n"
        "*Features:*\n"
        "• Multiple format conversion\n"  
        "• Bitrate selection (64-320 kbps)\n"
        "• Audio trimming/cutting\n"
        "• Volume normalization\n"
        "• Audio compression\n\n"
        "*Kaise use karein:*\n"
        "1. Mujhe koi audio file bhejein\n"
        "2. Feature select karein\n"
        "3. Settings adjust karein\n"
        "4. Converted file download karein\n\n"
        "Commands:\n"
        "/start - Bot start karein\n"
        "/help - Help dekhein\n"
        "/formats - Supported formats dekhein"
    )
    await update.message.reply_text(welcome_msg, parse_mode='Markdown')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Help command handler"""
    help_text = (
        "🔧 *Advanced Audio Converter Bot*\n\n"
        "*Features Available:*\n"
        "🎯 *Format Conversion* - MP3, WAV, OGG, M4A, FLAC, AAC\n"
        "⚡ *Bitrate Control* - 64kbps to 320kbps\n"
        "✂️ *Audio Trimming* - Start/end time set karein\n"
        "🔊 *Volume Normalization* - Audio volume optimize karein\n"
        "📊 *Compression* - File size reduce karein\n\n"
        "*Kaise use karein:*\n"
        "1️⃣ Audio file bhejein (document ya audio)\n"
        "2️⃣ Feature select karein\n"
        "3️⃣ Settings adjust karein\n"
        "4️⃣ Converted file receive karein\n\n"
        "⚠️ *Limits:*\n"
        "• File size: 20MB max\n"
        "• Trim duration: 1 minute max\n"
        "• Processing time: 2 minutes max"
    )
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def formats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show supported formats"""
    formats_text = "🎵 *Supported Audio Formats:*\n\n"
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
    
    # Audio ya document check karein
    if message.audio:
        file = message.audio
        file_name = file.file_name or "audio"
    elif message.document:
        file = message.document
        file_name = file.file_name
        # Check if it's audio file
        if not file_name or not any(file_name.lower().endswith(f'.{fmt}') for fmt in AUDIO_FORMATS.keys()):
            await message.reply_text("❌ Ye audio file nahi hai. Kripya audio file bhejein.")
            return
    else:
        return
    
    # File size check (20MB limit for free Telegram bot)
    if file.file_size > 20 * 1024 * 1024:
        await message.reply_text("❌ File bahut badi hai! Maximum 20MB allowed hai.")
        return
    
    # Processing message
    status_msg = await message.reply_text("⏳ Audio file download ho rahi hai...")
    
    try:
        # Download file
        new_file = await context.bot.get_file(file.file_id)
        input_path = os.path.join(TEMP_DIR, f"{user_id}_{file.file_unique_id}_{file_name}")
        await new_file.download_to_drive(input_path)
        
        # Store file info in user session
        user_sessions[user_id] = {
            'input_file': input_path,
            'original_name': file_name,
            'file_size': file.file_size
        }
        
        # Show main menu
        await show_main_menu(status_msg, user_id)
        
    except Exception as e:
        logger.error(f"Error downloading file: {e}")
        await status_msg.edit_text(f"❌ Error: {str(e)}")
        # Cleanup
        if 'input_path' in locals() and os.path.exists(input_path):
            os.remove(input_path)

async def show_main_menu(message, user_id):
    """Show main feature selection menu"""
    keyboard = [
        [InlineKeyboardButton("🎵 Format Convert", callback_data="menu_convert")],
        [InlineKeyboardButton("⚡ Bitrate Change", callback_data="menu_bitrate")],
        [InlineKeyboardButton("✂️ Trim Audio", callback_data="menu_trim")],
        [InlineKeyboardButton("🔊 Normalize Volume", callback_data="menu_normalize")],
        [InlineKeyboardButton("📊 Compress Audio", callback_data="menu_compress")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await message.edit_text(
        "✅ File download ho gayi!\n\n"
        "🎯 Kaunsa feature use karna hai?",
        reply_markup=reply_markup
    )

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Main callback handler"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
    data = query.data
    session = user_sessions.get(user_id)
    
    if not session or not os.path.exists(session['input_file']):
        await query.edit_message_text("❌ Session expired. Dobara audio bhejein.")
        return
    
    if data == "menu_convert":
        await show_format_selection(query)
    elif data == "menu_bitrate":
        await show_bitrate_selection(query)
    elif data == "menu_trim":
        await query.edit_message_text(
            "✂️ *Audio Trim*\n\n"
            "Start aur end time seconds mein bhejein.\n"
            "Example: `10 30` - 10sec se 30sec tak\n"
            "Ya `0 60` - start se 60sec tak\n\n"
            "Format: `start_time end_time`",
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

async def show_format_selection(query):
    """Show format selection keyboard"""
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
    await query.edit_message_text(
        "🎯 Kis format me convert karna hai?",
        reply_markup=reply_markup
    )

async def show_bitrate_selection(query):
    """Show bitrate selection keyboard"""
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
    await query.edit_message_text(
        "⚡ Konsa bitrate select karna hai?",
        reply_markup=reply_markup
    )

async def handle_format_conversion(query, output_format):
    """Handle format conversion"""
    user_id = query.from_user.id
    session = user_sessions.get(user_id)
    
    await query.edit_message_text(f"🔄 Converting to {output_format.upper()}...")
    
    try:
        # Load audio file
        audio = AudioSegment.from_file(session['input_file'])
        
        # Output file path
        base_name = os.path.splitext(session['original_name'])[0]
        output_file = os.path.join(TEMP_DIR, f"{user_id}_{base_name}_converted.{output_format}")
        
        # Convert audio with default settings
        audio.export(output_file, format=output_format, bitrate="192k")
        
        # Send converted file
        await query.message.reply_document(
            document=open(output_file, 'rb'),
            filename=f"{base_name}.{output_format}",
            caption=f"✅ Successfully converted to {output_format.upper()}!"
        )
        
        await query.edit_message_text("✅ Conversion complete! File bhej di gayi hai.")
        cleanup_files(session['input_file'], output_file)
        user_sessions.pop(user_id, None)
        
    except Exception as e:
        logger.error(f"Error converting audio: {e}")
        await query.edit_message_text(f"❌ Conversion failed: {str(e)}")
        cleanup_files(session['input_file'])
        user_sessions.pop(user_id, None)

async def handle_bitrate_conversion(query, bitrate):
    """Handle bitrate conversion"""
    user_id = query.from_user.id
    session = user_sessions.get(user_id)
    
    await query.edit_message_text(f"⚡ Changing bitrate to {bitrate}kbps...")
    
    try:
        # Load audio file
        audio = AudioSegment.from_file(session['input_file'])
        
        # Output file path (keep original format)
        original_ext = os.path.splitext(session['original_name'])[1][1:] or 'mp3'
        base_name = os.path.splitext(session['original_name'])[0]
        output_file = os.path.join(TEMP_DIR, f"{user_id}_{base_name}_{bitrate}kbps.{original_ext}")
        
        # Convert audio with selected bitrate
        audio.export(output_file, format=original_ext, bitrate=f"{bitrate}k")
        
        # Send converted file
        await query.message.reply_document(
            document=open(output_file, 'rb'),
            filename=f"{base_name}_{bitrate}kbps.{original_ext}",
            caption=f"✅ Bitrate changed to {bitrate}kbps!"
        )
        
        await query.edit_message_text("✅ Bitrate change complete! File bhej di gayi hai.")
        cleanup_files(session['input_file'], output_file)
        user_sessions.pop(user_id, None)
        
    except Exception as e:
        logger.error(f"Error changing bitrate: {e}")
        await query.edit_message_text(f"❌ Bitrate change failed: {str(e)}")
        cleanup_files(session['input_file'])
        user_sessions.pop(user_id, None)

async def handle_normalize_audio(query):
    """Handle volume normalization"""
    user_id = query.from_user.id
    session = user_sessions.get(user_id)
    
    await query.edit_message_text("🔊 Normalizing volume...")
    
    try:
        # Load audio file
        audio = AudioSegment.from_file(session['input_file'])
        
        # Normalize audio
        normalized_audio = normalize(audio)
        
        # Output file path
        base_name = os.path.splitext(session['original_name'])[0]
        output_file = os.path.join(TEMP_DIR, f"{user_id}_{base_name}_normalized.mp3")
        
        # Export normalized audio
        normalized_audio.export(output_file, format="mp3", bitrate="192k")
        
        # Send normalized file
        await query.message.reply_document(
            document=open(output_file, 'rb'),
            filename=f"{base_name}_normalized.mp3",
            caption="✅ Volume normalized successfully!"
        )
        
        await query.edit_message_text("✅ Volume normalization complete!")
        cleanup_files(session['input_file'], output_file)
        user_sessions.pop(user_id, None)
        
    except Exception as e:
        logger.error(f"Error normalizing audio: {e}")
        await query.edit_message_text(f"❌ Normalization failed: {str(e)}")
        cleanup_files(session['input_file'])
        user_sessions.pop(user_id, None)

async def handle_compress_audio(query):
    """Handle audio compression"""
    user_id = query.from_user.id
    session = user_sessions.get(user_id)
    
    await query.edit_message_text("📊 Compressing audio...")
    
    try:
        # Load audio file
        audio = AudioSegment.from_file(session['input_file'])
        
        # Output file path
        base_name = os.path.splitext(session['original_name'])[0]
        output_file = os.path.join(TEMP_DIR, f"{user_id}_{base_name}_compressed.mp3")
        
        # Compress with lower bitrate
        audio.export(output_file, format="mp3", bitrate="128k")
        
        # Send compressed file
        await query.message.reply_document(
            document=open(output_file, 'rb'),
            filename=f"{base_name}_compressed.mp3",
            caption="✅ Audio compressed successfully!"
        )
        
        await query.edit_message_text("✅ Compression complete! File bhej di gayi hai.")
        cleanup_files(session['input_file'], output_file)
        user_sessions.pop(user_id, None)
        
    except Exception as e:
        logger.error(f"Error compressing audio: {e}")
        await query.edit_message_text(f"❌ Compression failed: {str(e)}")
        cleanup_files(session['input_file'])
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
        
        start_time = int(times[0]) * 1000  # Convert to milliseconds
        end_time = int(times[1]) * 1000
        
        if start_time < 0 or end_time <= start_time:
            await update.message.reply_text("❌ Invalid times. End time should be greater than start time.")
            return
        
        await update.message.reply_text(f"✂️ Trimming from {times[0]}s to {times[1]}s...")
        
        # Load and trim audio
        audio = AudioSegment.from_file(session['input_file'])
        
        # Check if end time exceeds audio length
        if end_time > len(audio):
            end_time = len(audio)
            await update.message.reply_text("⚠️ End time adjusted to audio length.")
        
        trimmed_audio = audio[start_time:end_time]
        
        # Output file path
        base_name = os.path.splitext(session['original_name'])[0]
        output_file = os.path.join(TEMP_DIR, f"{user_id}_{base_name}_trimmed.mp3")
        
        # Export trimmed audio
        trimmed_audio.export(output_file, format="mp3", bitrate="192k")
        
        # Send trimmed file
        await update.message.reply_document(
            document=open(output_file, 'rb'),
            filename=f"{base_name}_trimmed.mp3",
            caption=f"✅ Audio trimmed from {times[0]}s to {times[1]}s!"
        )
        
        cleanup_files(session['input_file'], output_file)
        user_sessions.pop(user_id, None)
        
    except ValueError:
        await update.message.reply_text("❌ Invalid numbers. Please enter valid seconds.")
    except Exception as e:
        logger.error(f"Error trimming audio: {e}")
        await update.message.reply_text(f"❌ Trimming failed: {str(e)}")
        cleanup_files(session['input_file'])
        user_sessions.pop(user_id, None)

def cleanup_files(*files):
    """Cleanup temporary files"""
    for file_path in files:
        try:
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
        except Exception as e:
            logger.error(f"Error cleaning up {file_path}: {e}")

def main():
    """Main function"""
    # FFmpeg available hai ya nahi check karo
    try:
        subprocess.run([AudioSegment.ffmpeg, '-version'], check=True, capture_output=True)
        logger.info("FFmpeg successfully configured")
    except Exception as e:
        logger.error(f"FFmpeg configuration error: {e}")
    
    # Create application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("formats", formats_command))
    application.add_handler(MessageHandler(filters.AUDIO | filters.Document.AUDIO, handle_audio))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_trim_message))
    application.add_handler(CallbackQueryHandler(handle_callback, pattern="^menu_|^convert_|^bitrate_"))
    
    # Start bot
    logger.info("Bot shuru ho raha hai...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()