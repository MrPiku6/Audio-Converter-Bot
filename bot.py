import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from pydub import AudioSegment
import subprocess

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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command handler"""
    welcome_msg = (
        "🎵 *Audio Converter Bot me aapka swagat hai!* 🎵\n\n"
        "Main audio files ko convert kar sakta hu.\n\n"
        "*Supported Formats:*\n"
        "MP3, WAV, OGG, M4A, FLAC, AAC\n\n"
        "*Kaise use karein:*\n"
        "1. Mujhe koi audio file bhejein\n"
        "2. Convert karne ke liye format select karein\n"
        "3. Converted file download karein\n\n"
        "Commands:\n"
        "/start - Bot start karein\n"
        "/help - Help dekhein"
    )
    await update.message.reply_text(welcome_msg, parse_mode='Markdown')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Help command handler"""
    help_text = (
        "🔧 *Kaise use karein:*\n\n"
        "1️⃣ Mujhe audio file bhejein (as document ya audio)\n"
        "2️⃣ Format select karein\n"
        "3️⃣ Converted file receive karein\n\n"
        "*Supported Formats:*\n"
        "• MP3 (sabse common)\n"
        "• WAV (high quality)\n"
        "• OGG (compressed)\n"
        "• M4A (Apple format)\n"
        "• FLAC (lossless)\n"
        "• AAC (compressed)\n\n"
        "⚠️ *Note:* File size 20MB se kam honi chahiye"
    )
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Audio file handler"""
    message = update.message
    
    # Audio ya document check karein
    if message.audio:
        file = message.audio
        file_name = file.file_name or "audio"
    elif message.document:
        file = message.document
        file_name = file.file_name
        # Check if it's audio file
        if not any(file_name.lower().endswith(f'.{fmt}') for fmt in AUDIO_FORMATS.keys()):
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
        input_path = os.path.join(TEMP_DIR, f"{file.file_unique_id}_{file_name}")
        await new_file.download_to_drive(input_path)
        
        # Store file path in user data
        context.user_data['input_file'] = input_path
        context.user_data['original_name'] = file_name
        
        # Create format selection keyboard
        keyboard = []
        row = []
        for fmt, name in AUDIO_FORMATS.items():
            row.append(InlineKeyboardButton(name, callback_data=f"convert_{fmt}"))
            if len(row) == 3:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await status_msg.edit_text(
            "✅ File download ho gayi!\n\n"
            "🎯 Kis format me convert karna hai?",
            reply_markup=reply_markup
        )
        
    except Exception as e:
        logger.error(f"Error downloading file: {e}")
        await status_msg.edit_text(f"❌ Error: {str(e)}")
        # Cleanup
        if 'input_path' in locals() and os.path.exists(input_path):
            os.remove(input_path)

async def convert_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Audio conversion handler"""
    query = update.callback_query
    await query.answer()
    
    # Get format from callback data
    output_format = query.data.replace("convert_", "")
    
    # Get input file from user data
    input_file = context.user_data.get('input_file')
    original_name = context.user_data.get('original_name', 'audio')
    
    if not input_file or not os.path.exists(input_file):
        await query.edit_message_text("❌ File nahi mili. Dobara audio bhejein.")
        return
    
    # Processing message
    await query.edit_message_text(f"🔄 Converting to {output_format.upper()}...")
    
    try:
        # Load audio file
        audio = AudioSegment.from_file(input_file)
        
        # Output file path
        base_name = os.path.splitext(original_name)[0]
        output_file = os.path.join(TEMP_DIR, f"{base_name}_converted.{output_format}")
        
        # Convert audio
        audio.export(output_file, format=output_format)
        
        # Send converted file
        await query.message.reply_document(
            document=open(output_file, 'rb'),
            filename=f"{base_name}.{output_format}",
            caption=f"✅ Successfully converted to {output_format.upper()}!"
        )
        
        await query.edit_message_text(f"✅ Conversion complete! File bhej di gayi hai.")
        
        # Cleanup
        if os.path.exists(input_file):
            os.remove(input_file)
        if os.path.exists(output_file):
            os.remove(output_file)
        context.user_data.clear()
        
    except Exception as e:
        logger.error(f"Error converting audio: {e}")
        await query.edit_message_text(f"❌ Conversion failed: {str(e)}")
        # Cleanup
        if 'input_file' in locals() and os.path.exists(input_file):
            os.remove(input_file)
        if 'output_file' in locals() and os.path.exists(output_file):
            os.remove(output_file)
        context.user_data.clear()

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
    application.add_handler(MessageHandler(filters.AUDIO | filters.Document.AUDIO, handle_audio))
    application.add_handler(CallbackQueryHandler(convert_audio, pattern="^convert_"))
    
    # Start bot
    logger.info("Bot shuru ho raha hai...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()