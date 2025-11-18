"""Handler for /update command."""

import logging
from datetime import date

from telegram import Update
from telegram.ext import ContextTypes

import database
from handlers.add import parse_deadline

logger = logging.getLogger(__name__)


async def _update_price(product_id: int, asin: str, value_str: str, user_id: int, message) -> bool:
    """Update product price. Returns True if successful."""
    try:
        new_price = float(value_str.replace(",", "."))
        if new_price <= 0:
            raise ValueError("Price must be positive")
    except ValueError:
        await message.reply_text(
            f"❌ Prezzo non valido: `{value_str}`\n\nUsa un numero positivo (es. 59.90 o 59,90)",
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
            f"❌ Scadenza non valida: {e}\n\nUsa giorni (es. 30) o data ISO (es. 2024-12-25)"
        )
        return False

    if new_deadline < date.today():
        await message.reply_text(
            "❌ La scadenza deve essere nel futuro!\n\n"
            f"Data specificata: {new_deadline.strftime('%d/%m/%Y')}"
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
            "La soglia deve essere un numero positivo minore del prezzo pagato."
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


async def update_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle /update command.

    Format: /update <numero> <campo> <valore>
    Examples:
    - /update 1 prezzo 55.00
    - /update 1 scadenza 2024-12-30
    - /update 1 soglia 10

    Args:
        update: Telegram update object
        context: Telegram context object
    """
    user_id = update.effective_user.id

    # Check arguments
    if not context.args or len(context.args) != 3:
        await update.message.reply_text(
            "❌ *Utilizzo:* `/update <numero> <campo> <valore>`\n\n"
            "*Esempi:*\n"
            "`/update 1 prezzo 55.00`\n"
            "`/update 1 scadenza 2024-12-30`\n"
            "`/update 1 soglia 10`\n\n"
            "*Campi disponibili:*\n"
            "• `prezzo` - Prezzo pagato in euro\n"
            "• `scadenza` - Data scadenza reso (giorni o data ISO)\n"
            "• `soglia` - Soglia minima di risparmio in euro",
            parse_mode="Markdown",
        )
        return

    product_number_str = context.args[0]
    field = context.args[1].lower()
    value_str = context.args[2]

    logger.info(f"User {user_id} updating product #{product_number_str}: {field}={value_str}")

    try:
        # Parse product number
        try:
            product_number = int(product_number_str)
            if product_number < 1:
                raise ValueError("Product number must be positive")
        except ValueError:
            await update.message.reply_text(
                f"❌ Numero prodotto non valido: `{product_number_str}`\n\n"
                "Usa un numero intero positivo (es. 1, 2, 3...).\n"
                "Vedi /list per i numeri dei tuoi prodotti.",
                parse_mode="Markdown",
            )
            return

        # Validate field name
        valid_fields = ["prezzo", "scadenza", "soglia"]
        if field not in valid_fields:
            await update.message.reply_text(
                f"❌ Campo non valido: `{field}`\n\n"
                "Campi disponibili: `prezzo`, `scadenza`, `soglia`",
                parse_mode="Markdown",
            )
            return

        # Get user's products
        products = await database.get_user_products(user_id)

        if not products:
            await update.message.reply_text(
                "📭 *Non hai prodotti da aggiornare*\n\nUsa /add per aggiungere un prodotto!",
                parse_mode="Markdown",
            )
            return

        # Validate product number is in range
        if product_number > len(products):
            await update.message.reply_text(
                f"❌ Numero prodotto non valido: {product_number}\n\n"
                f"Hai solo {len(products)} prodotto/i monitorato/i.\n"
                "Usa /list per vedere la tua lista."
            )
            return

        # Get product to update (convert 1-based to 0-based index)
        product = products[product_number - 1]
        product_id = product["id"]
        asin = product["asin"]

        # Update field based on user input
        if field == "prezzo":
            await _update_price(product_id, asin, value_str, user_id, update.message)
        elif field == "scadenza":
            await _update_deadline(product_id, asin, value_str, user_id, update.message)
        elif field == "soglia":
            current_price = product["price_paid"]
            await _update_threshold(
                product_id, asin, value_str, current_price, user_id, update.message
            )

    except Exception as e:
        logger.error(f"Error in update_handler for user {user_id}: {e}", exc_info=True)
        await update.message.reply_text("❌ Errore nell'aggiornare il prodotto. Riprova più tardi.")
