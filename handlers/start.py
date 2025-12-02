"""Handler for /start command."""

import logging
import os

from telegram import Update
from telegram.ext import ContextTypes

import database

logger = logging.getLogger(__name__)


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle /start command.

    Registers new users and shows welcome message with bot instructions.
    Supports referral links: /start <referrer_user_id>

    Args:
        update: Telegram update object
        context: Telegram context object
    """
    user = update.effective_user
    user_id = user.id
    language_code = user.language_code

    logger.info(f"User {user_id} started the bot")

    # Parse referral code (if present)
    referred_by = None
    referral_invalid_message = None

    if context.args:
        referral_code = context.args[0]
        # Validate referral code (must be positive integer)
        if referral_code.isdigit():
            referrer_id = int(referral_code)
            if referrer_id > 0 and referrer_id != user_id:
                # Check if referrer exists
                referrer = await database.get_user(referrer_id)
                if referrer:
                    referred_by = referrer_id
                    logger.info(f"User {user_id} referred by {referrer_id}")
                else:
                    # Referrer doesn't exist
                    referral_invalid_message = (
                        "ℹ️ Il codice di invito che hai usato non è valido "
                        "(l'invitante non risulta esistente).\n\n"
                    )
                    logger.warning(f"User {user_id} used invalid referral code {referrer_id}")
            elif referrer_id == user_id:
                # Self-referral attempt (silently ignore)
                logger.warning(f"User {user_id} attempted self-referral")
        else:
            # Invalid format
            logger.warning(f"User {user_id} used malformed referral code: {referral_code}")

    # Register user in database if not exists
    existing_user = None
    try:
        existing_user = await database.get_user(user_id)
        if not existing_user:
            # New user: add to DB with referral
            await database.add_user(
                user_id=user_id, language_code=language_code, referred_by=referred_by
            )

            # Set initial product limit
            if referred_by:
                # Invited user gets bonus: 3 base + 3 invited bonus = 6 slots
                initial_slots = database.INITIAL_MAX_PRODUCTS + database.INVITED_USER_BONUS
                await database.set_user_max_products(user_id, initial_slots)
                logger.info(
                    f"New user {user_id} registered with {initial_slots} product slots "
                    f"(referred by {referred_by})"
                )
            else:
                # Regular user: 3 slots
                await database.set_user_max_products(user_id, database.INITIAL_MAX_PRODUCTS)
                logger.info(
                    f"New user {user_id} registered with {database.INITIAL_MAX_PRODUCTS} product slots"
                )
    except Exception as e:
        logger.error(f"Error registering user {user_id}: {e}", exc_info=True)

    # Build welcome message
    welcome_message = ""

    # Add referral invalid message if applicable (only for new users with invalid code)
    if referral_invalid_message and not existing_user:
        welcome_message += referral_invalid_message

    welcome_message += (
        "👋 <b>Benvenuto su RepackIt!</b>\n\n"
        "Ti aiuto a risparmiare monitorando i prezzi Amazon durante il periodo di reso.\n\n"
    )

    # Add referral bonus message for invited new users
    if not existing_user and referred_by:
        welcome_message += (
            "🎁 <b>Hai ricevuto 3 slot bonus</b> per essere stato invitato!\n"
            "Hai 6 slot disponibili per monitorare i tuoi prodotti.\n\n"
        )

    welcome_message += (
        "<b>Come funziona:</b>\n"
        "1️⃣ Aggiungi un prodotto che hai già acquistato\n"
        "2️⃣ Controllo il prezzo ogni giorno\n"
        "3️⃣ Ti avviso se scende, così puoi fare un nuovo ordine e restituire il precedente!\n\n"
        "<b>Comandi disponibili:</b>\n"
        "/add - Aggiungi un prodotto da monitorare\n"
        "/list - Visualizza i tuoi prodotti\n"
        "/delete - Rimuovi un prodotto\n"
        "/update - Modifica un prodotto\n"
        "/feedback - Invia un feedback\n\n"
        "Usa /help per maggiori informazioni!"
    )

    # Add channel reference if configured
    telegram_channel = os.getenv("TELEGRAM_CHANNEL", "").strip()
    if telegram_channel:
        welcome_message += f"\n\n📢 Seguici su {telegram_channel} per aggiornamenti e novità!"

    await update.message.reply_text(welcome_message, parse_mode="HTML")
