"""Handler for /start command."""

import logging

from telegram import Update
from telegram.ext import ContextTypes

import database

logger = logging.getLogger(__name__)


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle /start command.

    Registers new users and shows welcome message with bot instructions.

    Args:
        update: Telegram update object
        context: Telegram context object
    """
    user = update.effective_user
    user_id = user.id
    language_code = user.language_code

    logger.info(f"User {user_id} started the bot")

    # Register user in database if not exists
    try:
        existing_user = await database.get_user(user_id)
        if not existing_user:
            # New user: add to DB and set initial product limit
            await database.add_user(user_id=user_id, language_code=language_code)
            await database.set_user_max_products(user_id, database.INITIAL_MAX_PRODUCTS)
            logger.info(
                f"New user {user_id} registered with {database.INITIAL_MAX_PRODUCTS} product slots"
            )
    except Exception as e:
        logger.error(f"Error registering user {user_id}: {e}", exc_info=True)

    # Send welcome message
    welcome_message = (
        "👋 *Benvenuto su RepackIt!*\n\n"
        "Ti aiuto a risparmiare monitorando i prezzi Amazon durante il periodo di reso.\n\n"
        "*Come funziona:*\n"
        "1️⃣ Aggiungi un prodotto che hai già acquistato\n"
        "2️⃣ Controllo il prezzo ogni giorno\n"
        "3️⃣ Ti avviso se scende, così puoi fare un nuovo ordine e restituire il precedente!\n\n"
        "*Comandi disponibili:*\n"
        "/add - Aggiungi un prodotto da monitorare\n"
        "/list - Visualizza i tuoi prodotti\n"
        "/delete - Rimuovi un prodotto\n"
        "/update - Modifica un prodotto\n"
        "/feedback - Invia un feedback\n\n"
        "Usa /help per maggiori informazioni!"
    )

    await update.message.reply_text(welcome_message, parse_mode="Markdown")
