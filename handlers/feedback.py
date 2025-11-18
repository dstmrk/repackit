"""Handler for /feedback command."""

import logging

from telegram import Update
from telegram.ext import ContextTypes

import database

logger = logging.getLogger(__name__)


async def feedback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle /feedback command.

    Format: /feedback <messaggio>
    Example: /feedback Il bot funziona benissimo, grazie!

    Args:
        update: Telegram update object
        context: Telegram context object
    """
    user_id = update.effective_user.id

    # Check arguments
    if not context.args:
        await update.message.reply_text(
            "❌ *Utilizzo:* `/feedback <messaggio>`\n\n"
            "*Esempio:*\n"
            "`/feedback Il bot funziona benissimo, grazie!`\n\n"
            "Scrivi il tuo feedback dopo il comando.",
            parse_mode="Markdown",
        )
        return

    # Join all arguments to form the complete message
    feedback_message = " ".join(context.args)

    logger.info(f"User {user_id} submitting feedback: {feedback_message[:50]}...")

    try:
        # Save feedback to database
        feedback_id = await database.add_feedback(user_id, feedback_message)

        await update.message.reply_text(
            "✅ *Feedback ricevuto!*\n\n"
            "Grazie per il tuo feedback! "
            "Lo esamineremo al più presto per migliorare il servizio.\n\n"
            "Se hai altre domande, usa /start per vedere tutti i comandi disponibili.",
            parse_mode="Markdown",
        )

        logger.info(f"Feedback {feedback_id} saved from user {user_id}")

    except Exception as e:
        logger.error(f"Error in feedback_handler for user {user_id}: {e}", exc_info=True)
        await update.message.reply_text("❌ Errore nel salvare il feedback. Riprova più tardi.")
