"""Handler for /help command."""

import logging

from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle /help command.

    Shows all available commands with descriptions.

    Args:
        update: Telegram update object
        context: Telegram context object
    """
    user_id = update.effective_user.id

    logger.info(f"User {user_id} requested help")

    help_message = (
        "📖 <b>Comandi disponibili</b>\n\n"
        "<b>Gestione prodotti:</b>\n"
        "/add - Aggiungi un prodotto da monitorare\n"
        "/list - Mostra i tuoi prodotti monitorati\n"
        "/delete - Rimuovi un prodotto dalla lista\n"
        "/update - Modifica i dati di un prodotto\n\n"
        "<b>Informazioni e supporto:</b>\n"
        "/start - Messaggio di benvenuto\n"
        "/help - Mostra questo messaggio\n"
        "/feedback - Invia feedback o segnala problemi\n\n"
        "<b>Come funziona?</b>\n"
        "1️⃣ Usa /add per aggiungere un prodotto Amazon.it che hai acquistato\n"
        "2️⃣ Il bot controllerà il prezzo ogni giorno\n"
        "3️⃣ Riceverai una notifica se il prezzo scende\n"
        "4️⃣ Potrai decidere in autonomia di riordinare il prodotto e fare il reso del precedente ordine\n\n"
        "<i>Il monitoraggio si ferma automaticamente alla scadenza del reso.</i>"
    )

    await update.message.reply_text(help_message, parse_mode="HTML")

    logger.info(f"Help message sent to user {user_id}")
