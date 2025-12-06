"""Handler for /feedback command with conversational flow."""

import logging
from datetime import datetime

from telegram import Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

import database
from config import get_config
from utils import keyboards, messages

logger = logging.getLogger(__name__)

# Load configuration
cfg = get_config()

# Constants from config
MIN_FEEDBACK_LENGTH = cfg.feedback_min_length
MAX_FEEDBACK_LENGTH = cfg.feedback_max_length
FEEDBACK_RATE_LIMIT_HOURS = cfg.feedback_rate_limit_hours

# Conversation state
WAITING_FEEDBACK_MESSAGE = 0


def _format_time_remaining(hours_remaining: float) -> str:
    """
    Format remaining time as human-readable string.

    Args:
        hours_remaining: Hours remaining until next feedback allowed

    Returns:
        Formatted string like "22 ore" or "30 minuti"
    """
    if hours_remaining >= 1:
        hour_count = int(hours_remaining)
        return f"{hour_count} or{'a' if hour_count == 1 else 'e'}"

    minutes_remaining = int(hours_remaining * 60)
    return f"{minutes_remaining} minut{'o' if minutes_remaining == 1 else 'i'}"


async def start_feedback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Start the /feedback conversation flow.

    Step 1: Check rate limit, then ask for feedback message.
    """
    user_id = update.effective_user.id

    logger.info(f"User {user_id} started /feedback command")

    # Check rate limit (24 hours)
    last_feedback_time = await database.get_last_feedback_time(user_id)

    if last_feedback_time:
        try:
            # Parse the timestamp (SQLite returns ISO format)
            last_time = datetime.fromisoformat(last_feedback_time)
            time_since_last = datetime.now() - last_time
            hours_since_last = time_since_last.total_seconds() / 3600

            if hours_since_last < FEEDBACK_RATE_LIMIT_HOURS:
                # Calculate and format remaining time
                hours_remaining = FEEDBACK_RATE_LIMIT_HOURS - hours_since_last
                time_str = _format_time_remaining(hours_remaining)

                logger.info(
                    f"User {user_id} rate limited: {hours_since_last:.1f}h since last feedback"
                )

                await update.message.reply_text(
                    f"⏳ <b>Limite raggiunto</b>\n\n"
                    f"Puoi inviare un nuovo feedback tra circa <b>{time_str}</b>.\n\n"
                    "Questo limite aiuta a prevenire lo spam e garantisce "
                    "che ogni feedback riceva la giusta attenzione. 🙏",
                    parse_mode="HTML",
                )
                return ConversationHandler.END

        except (ValueError, TypeError) as e:
            # If timestamp parsing fails, allow feedback (fail open)
            logger.warning(f"Error parsing last_feedback_time for user {user_id}: {e}")

    # Rate limit passed, proceed with feedback flow
    await update.message.reply_text(
        "💬 <b>Invia il tuo feedback</b>\n\n"
        "Scrivi il tuo feedback, suggerimento o segnalazione di bug.\n\n"
        f"<i>Minimo {MIN_FEEDBACK_LENGTH} caratteri, massimo {MAX_FEEDBACK_LENGTH} caratteri.</i>\n\n"
        "Oppure scrivi /cancel per annullare.",
        parse_mode="HTML",
    )

    return WAITING_FEEDBACK_MESSAGE


async def handle_feedback_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Handle feedback message input.

    Step 2: Validate and show confirmation with inline buttons.
    """
    user_id = update.effective_user.id
    feedback_message = update.message.text.strip()

    # Validate length
    if len(feedback_message) < MIN_FEEDBACK_LENGTH:
        await update.message.reply_text(
            f"❌ <b>Feedback troppo breve!</b>\n\n"
            f"Il feedback deve contenere almeno <b>{MIN_FEEDBACK_LENGTH} caratteri</b>.\n"
            f"Attualmente: {len(feedback_message)} caratteri.\n\n"
            "Riprova oppure /cancel per annullare.",
            parse_mode="HTML",
        )
        return WAITING_FEEDBACK_MESSAGE

    if len(feedback_message) > MAX_FEEDBACK_LENGTH:
        await update.message.reply_text(
            f"❌ <b>Feedback troppo lungo!</b>\n\n"
            f"Il feedback non può superare <b>{MAX_FEEDBACK_LENGTH} caratteri</b>.\n"
            f"Attualmente: {len(feedback_message)} caratteri.\n\n"
            "Riprova con un messaggio più breve oppure /cancel per annullare.",
            parse_mode="HTML",
        )
        return WAITING_FEEDBACK_MESSAGE

    logger.info(f"User {user_id} provided valid feedback ({len(feedback_message)} chars)")

    # Store feedback in context
    context.user_data["feedback_message"] = feedback_message

    # Show preview with confirmation buttons
    reply_markup = keyboards.confirm_cancel_keyboard(
        confirm_text="✅ Sì, invia",
        confirm_callback="feedback_send",
        cancel_callback="feedback_cancel",
    )

    # Truncate preview if too long
    preview = feedback_message if len(feedback_message) <= 200 else feedback_message[:200] + "..."

    await update.message.reply_text(
        f"📝 <b>Anteprima del tuo feedback:</b>\n\n<i>{preview}</i>\n\n"
        f"Lunghezza: {len(feedback_message)} caratteri\n\n"
        "Vuoi inviare questo feedback?",
        parse_mode="HTML",
        reply_markup=reply_markup,
    )

    return ConversationHandler.END  # Wait for callback


async def handle_feedback_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle feedback confirmation (send/cancel).

    Called when user clicks inline button.
    """
    query = update.callback_query
    user_id = update.effective_user.id

    await query.answer()

    callback_data = query.data

    if callback_data == "feedback_cancel":
        await query.edit_message_text(
            messages.cancel_feedback(),
            parse_mode="HTML",
        )
        context.user_data.clear()
        logger.info(f"User {user_id} cancelled feedback")
        return

    if callback_data == "feedback_send":
        feedback_message = context.user_data.get("feedback_message")

        if not feedback_message:
            await query.edit_message_text(
                "❌ Errore: feedback non trovato. Riprova con /feedback.",
            )
            context.user_data.clear()
            return

        try:
            # Save feedback to database
            feedback_id = await database.add_feedback(user_id, feedback_message)

            await query.edit_message_text(
                messages.feedback_success(),
                parse_mode="HTML",
            )

            logger.info(
                f"Feedback {feedback_id} saved from user {user_id} ({len(feedback_message)} chars)"
            )

        except Exception as e:
            logger.error(f"Error saving feedback from user {user_id}: {e}", exc_info=True)
            await query.edit_message_text("❌ Errore nel salvare il feedback. Riprova più tardi.")

        context.user_data.clear()


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel the conversation."""
    await update.message.reply_text(
        messages.cancel_feedback(),
        parse_mode="HTML",
    )
    context.user_data.clear()
    return ConversationHandler.END


# Conversation handler
feedback_conversation_handler = ConversationHandler(
    entry_points=[CommandHandler("feedback", start_feedback)],
    states={
        WAITING_FEEDBACK_MESSAGE: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_feedback_message)
        ],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
)

# Callback handler for confirmation buttons
feedback_callback_handler = CallbackQueryHandler(
    handle_feedback_confirmation, pattern="^feedback_(send|cancel)$"
)
