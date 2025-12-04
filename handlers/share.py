"""Handler for /share command."""

import logging
from urllib.parse import quote

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

import database

logger = logging.getLogger(__name__)


async def share_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle /share command.

    Shows user's referral link and explains the referral system.

    Args:
        update: Telegram update object
        context: Telegram context object
    """
    user_id = update.effective_user.id

    logger.info(f"User {user_id} requested /share")

    # Get user's current slot count
    try:
        current_slots = await database.get_user_product_limit(user_id)
        max_slots = database.DEFAULT_MAX_PRODUCTS
    except Exception as e:
        logger.error(f"Error getting user slots for {user_id}: {e}", exc_info=True)
        await update.message.reply_text(
            "❌ Errore nel recuperare i tuoi dati. Riprova più tardi.", parse_mode="HTML"
        )
        return

    # Build referral link
    bot_username = context.bot.username
    referral_link = f"https://t.me/{bot_username}?start={user_id}"

    # Build share message
    share_message = (
        "🎁 <b>Invita i tuoi amici e guadagna più slot!</b>\n\n"
        f"📊 I tuoi slot prodotto: <b>{current_slots}/{max_slots}</b>\n\n"
        "<b>Come funziona:</b>\n"
        "1️⃣ Condividi il tuo link personale\n"
        "2️⃣ Il tuo amico riceve 6 slot (invece di 3)\n"
        "3️⃣ Quando aggiunge il primo prodotto, <b>tu ricevi +3 slot</b>!\n\n"
        f"Puoi guadagnare fino a <b>{max_slots} slot</b> invitando amici.\n\n"
        "🔗 <b>Il tuo link di invito:</b>\n"
        f"<code>{referral_link}</code>"
    )

    # Build share button (pre-filled message)
    share_text = (
        f"🎁 Risparmia sui tuoi acquisti Amazon con @{bot_username}! "
        "Monitora i prezzi e ricevi notifiche quando scendono. "
        "Usa il mio link per ricevere 6 slot bonus!"
    )
    share_url = f"https://t.me/share/url?url={referral_link}&text={quote(share_text)}"

    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("📤 Condividi con un amico", url=share_url)]]
    )

    await update.message.reply_text(
        share_message, parse_mode="HTML", disable_web_page_preview=True, reply_markup=keyboard
    )

    logger.info(f"Share message sent to user {user_id} (slots: {current_slots}/{max_slots})")
