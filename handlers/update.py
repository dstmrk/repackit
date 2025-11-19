"""Handler for /update command with conversational flow."""

import logging
import warnings
from datetime import date

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)
from telegram.warnings import PTBUserWarning

import database
from handlers.add import parse_deadline

# Suppress PTBUserWarning for per_message=False in ConversationHandler
# This is intentional - we want per-conversation tracking, not per-message
warnings.filterwarnings("ignore", category=PTBUserWarning)

logger = logging.getLogger(__name__)

# Constants
CANCEL_MESSAGE = "❌ *Operazione annullata*\n\nNessuna modifica è stata effettuata."

# Conversation states
WAITING_PRODUCT_SELECTION, WAITING_FIELD_SELECTION, WAITING_VALUE_INPUT = range(3)


async def start_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Start the /update conversation flow.

    Step 1: Show list of products with inline buttons.
    """
    user_id = update.effective_user.id

    logger.info(f"User {user_id} started /update flow")

    # Get user's products
    products = await database.get_user_products(user_id)

    if not products:
        await update.message.reply_text(
            "📭 *Non hai prodotti da aggiornare*\n\nUsa /add per aggiungere un prodotto!",
            parse_mode="Markdown",
        )
        return ConversationHandler.END

    # Create inline keyboard with one button per product
    keyboard = []
    for idx, product in enumerate(products, start=1):
        product_name = product.get("product_name") or f"Prodotto #{idx}"
        price_paid = product["price_paid"]

        button_text = f"{idx}. {product_name} - €{price_paid:.2f}"
        callback_data = f"update_product_{product['id']}"

        keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])

    # Add cancel button
    keyboard.append([InlineKeyboardButton("❌ Annulla", callback_data="update_cancel")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "🔄 *Aggiorna un prodotto*\n\nSeleziona il prodotto che vuoi modificare:",
        parse_mode="Markdown",
        reply_markup=reply_markup,
    )

    return WAITING_PRODUCT_SELECTION


async def handle_product_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Handle product selection.

    Step 2: Show fields that can be updated with inline buttons.
    """
    query = update.callback_query
    user_id = update.effective_user.id

    await query.answer()

    callback_data = query.data

    # Handle cancel
    if callback_data == "update_cancel":
        await query.edit_message_text(
            CANCEL_MESSAGE,
            parse_mode="Markdown",
        )
        return ConversationHandler.END

    # Extract product_id
    product_id = int(callback_data.replace("update_product_", ""))

    # Get product details
    products = await database.get_user_products(user_id)
    product = next((p for p in products if p["id"] == product_id), None)

    if product is None:
        await query.edit_message_text("❌ Prodotto non trovato. Potrebbe essere stato eliminato.")
        return ConversationHandler.END

    # Store product info in context
    context.user_data["update_product_id"] = product_id
    context.user_data["update_product_name"] = product.get("product_name") or "Prodotto"
    context.user_data["update_product_asin"] = product["asin"]
    context.user_data["update_product_price_paid"] = product["price_paid"]

    logger.info(f"User {user_id} selected product_id={product_id} for update")

    product_display = product.get("product_name") or f"ASIN {product['asin']}"

    # Create inline keyboard for field selection
    keyboard = [
        [InlineKeyboardButton("📦 Nome prodotto", callback_data="update_field_nome")],
        [InlineKeyboardButton("💰 Prezzo pagato", callback_data="update_field_prezzo")],
        [InlineKeyboardButton("📅 Scadenza reso", callback_data="update_field_scadenza")],
        [InlineKeyboardButton("🎯 Soglia risparmio", callback_data="update_field_soglia")],
        [InlineKeyboardButton("❌ Annulla", callback_data="update_cancel")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        f"📦 *Prodotto selezionato:* {product_display}\n\n" "Cosa vuoi modificare?",
        parse_mode="Markdown",
        reply_markup=reply_markup,
    )

    return WAITING_FIELD_SELECTION


async def handle_field_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Handle field selection.

    Step 3: Ask for new value based on selected field.
    """
    query = update.callback_query
    user_id = update.effective_user.id

    await query.answer()

    callback_data = query.data

    # Handle cancel
    if callback_data == "update_cancel":
        await query.edit_message_text(
            CANCEL_MESSAGE,
            parse_mode="Markdown",
        )
        context.user_data.clear()
        return ConversationHandler.END

    # Extract field name
    field = callback_data.replace("update_field_", "")
    context.user_data["update_field"] = field

    logger.info(f"User {user_id} selected field={field} for update")

    # Show appropriate message based on field
    if field == "nome":
        current_name = context.user_data["update_product_name"]
        message = (
            "📦 *Aggiorna nome prodotto*\n\n"
            f"Nome attuale: *{current_name}*\n\n"
            "Inviami il nuovo nome (tra 3 e 100 caratteri).\n\n"
            "Esempio: `iPhone 15 Pro` oppure `Cuffie Sony`\n\n"
            "Oppure scrivi /cancel per annullare."
        )
    elif field == "prezzo":
        message = (
            "💰 *Aggiorna prezzo pagato*\n\n"
            "Inviami il nuovo prezzo in euro.\n\n"
            "Esempio: `59.90` oppure `59,90`\n\n"
            "Oppure scrivi /cancel per annullare."
        )
    elif field == "scadenza":
        message = (
            "📅 *Aggiorna scadenza reso*\n\n"
            "Inviami la nuova scadenza.\n\n"
            "Puoi inviarmi:\n"
            "• Un numero di giorni (da 1 a 365)\n"
            "  Esempio: `30`\n\n"
            "• Una data nel formato gg-mm-aaaa\n"
            "  Esempio: `09-05-2025`\n\n"
            "Oppure scrivi /cancel per annullare."
        )
    elif field == "soglia":
        current_price = context.user_data["update_product_price_paid"]
        message = (
            "🎯 *Aggiorna soglia risparmio*\n\n"
            "Inviami la nuova soglia minima di risparmio in euro.\n\n"
            f"Deve essere minore del prezzo pagato (€{current_price:.2f})\n\n"
            "Esempio: `5.00` oppure `5,00`\n\n"
            "Oppure scrivi /cancel per annullare."
        )

    await query.edit_message_text(message, parse_mode="Markdown")

    return WAITING_VALUE_INPUT


async def handle_value_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Handle value input and update the product.

    Step 4: Validate and save the new value.
    """
    user_id = update.effective_user.id
    value_str = update.message.text.strip()

    # Get stored data
    product_id = context.user_data["update_product_id"]
    asin = context.user_data["update_product_asin"]
    field = context.user_data["update_field"]

    logger.info(f"User {user_id} provided value for {field}: {value_str}")

    try:
        # Update based on field
        if field == "nome":
            product_name = context.user_data["update_product_name"]
            success = await _update_name(
                product_id, product_name, value_str, user_id, update.message
            )
        elif field == "prezzo":
            success = await _update_price(product_id, asin, value_str, user_id, update.message)
        elif field == "scadenza":
            success = await _update_deadline(product_id, asin, value_str, user_id, update.message)
        elif field == "soglia":
            current_price = context.user_data["update_product_price_paid"]
            success = await _update_threshold(
                product_id, asin, value_str, current_price, user_id, update.message
            )
        else:
            success = False

        if success:
            # Clear user_data and end conversation
            context.user_data.clear()
            return ConversationHandler.END
        else:
            # Keep in same state to retry
            return WAITING_VALUE_INPUT

    except Exception as e:
        logger.error(f"Error in handle_value_input for user {user_id}: {e}", exc_info=True)
        await update.message.reply_text("❌ Errore nell'aggiornare il prodotto. Riprova più tardi.")
        context.user_data.clear()
        return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel the conversation."""
    await update.message.reply_text(CANCEL_MESSAGE, parse_mode="Markdown")
    context.user_data.clear()
    return ConversationHandler.END


async def _update_name(
    product_id: int, old_name: str, value_str: str, user_id: int, message
) -> bool:
    """Update product name. Returns True if successful."""
    new_name = value_str.strip()

    # Validate length (between 3 and 100 characters)
    if len(new_name) < 3:
        await message.reply_text(
            "❌ *Nome troppo corto*\n\n"
            "Il nome del prodotto deve contenere almeno 3 caratteri.\n\n"
            "Riprova oppure /cancel per annullare.",
            parse_mode="Markdown",
        )
        return False

    if len(new_name) > 100:
        await message.reply_text(
            "❌ *Nome troppo lungo*\n\n"
            "Il nome del prodotto può contenere al massimo 100 caratteri.\n\n"
            "Riprova oppure /cancel per annullare.",
            parse_mode="Markdown",
        )
        return False

    await database.update_product(product_id, product_name=new_name)
    await message.reply_text(
        "✅ *Nome aggiornato con successo!*\n\n"
        f"📦 Nuovo nome: *{new_name}*",
        parse_mode="Markdown",
    )
    logger.info(
        f"Product name updated for user {user_id}: product_id={product_id}, new_name={new_name}"
    )
    return True


async def _update_price(product_id: int, asin: str, value_str: str, user_id: int, message) -> bool:
    """Update product price. Returns True if successful."""
    try:
        new_price = float(value_str.replace(",", "."))
        if new_price <= 0:
            raise ValueError("Price must be positive")
    except ValueError:
        await message.reply_text(
            f"❌ Prezzo non valido: `{value_str}`\n\nUsa un numero positivo (es. 59.90 o 59,90)\n\n"
            "Riprova oppure /cancel per annullare.",
            parse_mode="Markdown",
        )
        return False

    await database.update_product(product_id, price_paid=new_price)
    await message.reply_text(
        "✅ *Prezzo aggiornato con successo!*\n\n"
        f"📦 ASIN: `{asin}`\n"
        f"💰 Nuovo prezzo: €{new_price:.2f}",
        parse_mode="Markdown",
    )
    logger.info(f"Price updated for user {user_id}: product_id={product_id}, new_price={new_price}")
    return True


async def _update_deadline(
    product_id: int, asin: str, value_str: str, user_id: int, message
) -> bool:
    """Update product deadline. Returns True if successful."""
    try:
        new_deadline = parse_deadline(value_str)
    except ValueError as e:
        await message.reply_text(
            f"❌ Scadenza non valida: {e}\n\n"
            "Usa giorni (es. 30) o data gg-mm-aaaa (es. 09-05-2025)\n\n"
            "Riprova oppure /cancel per annullare."
        )
        return False

    if new_deadline < date.today():
        await message.reply_text(
            "❌ La scadenza deve essere nel futuro!\n\n"
            f"Data specificata: {new_deadline.strftime('%d/%m/%Y')}\n\n"
            "Riprova oppure /cancel per annullare."
        )
        return False

    await database.update_product(product_id, return_deadline=new_deadline)

    days_remaining = (new_deadline - date.today()).days
    await message.reply_text(
        "✅ *Scadenza aggiornata con successo!*\n\n"
        f"📦 ASIN: `{asin}`\n"
        f"📅 Nuova scadenza: {new_deadline.strftime('%d/%m/%Y')} (tra {days_remaining} giorni)",
        parse_mode="Markdown",
    )
    logger.info(
        f"Deadline updated for user {user_id}: product_id={product_id}, new_deadline={new_deadline}"
    )
    return True


async def _update_threshold(
    product_id: int, asin: str, value_str: str, current_price: float, user_id: int, message
) -> bool:
    """Update product threshold. Returns True if successful."""
    try:
        new_threshold = float(value_str.replace(",", "."))
        if new_threshold < 0:
            raise ValueError("Threshold must be non-negative")
        if new_threshold >= current_price:
            raise ValueError("Threshold must be less than price paid")
    except ValueError as e:
        await message.reply_text(
            f"❌ Soglia non valida: {e}\n\n"
            "La soglia deve essere un numero positivo minore del prezzo pagato.\n\n"
            "Riprova oppure /cancel per annullare."
        )
        return False

    await database.update_product(product_id, min_savings_threshold=new_threshold)
    await message.reply_text(
        "✅ *Soglia aggiornata con successo!*\n\n"
        f"📦 ASIN: `{asin}`\n"
        f"🎯 Nuova soglia risparmio: €{new_threshold:.2f}",
        parse_mode="Markdown",
    )
    logger.info(
        f"Threshold updated for user {user_id}: product_id={product_id}, new_threshold={new_threshold}"
    )
    return True


# Create the ConversationHandler
update_conversation_handler = ConversationHandler(
    entry_points=[CommandHandler("update", start_update)],
    states={
        WAITING_PRODUCT_SELECTION: [
            CallbackQueryHandler(handle_product_selection, pattern="^update_(product|cancel)_")
        ],
        WAITING_FIELD_SELECTION: [
            CallbackQueryHandler(handle_field_selection, pattern="^update_(field|cancel)_")
        ],
        WAITING_VALUE_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_value_input)],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
    per_message=False,  # Suppress PTBUserWarning - we want per-conversation tracking
)
