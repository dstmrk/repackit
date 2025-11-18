"""Handler for /delete command."""

import logging

from telegram import Update
from telegram.ext import ContextTypes

import database

logger = logging.getLogger(__name__)


async def delete_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle /delete command.

    Format: /delete <numero>
    Example: /delete 2

    Args:
        update: Telegram update object
        context: Telegram context object
    """
    user_id = update.effective_user.id

    # Check arguments
    if not context.args or len(context.args) != 1:
        await update.message.reply_text(
            "❌ *Utilizzo:* `/delete <numero>`\n\n"
            "*Esempio:*\n"
            "`/delete 2` - Rimuove il secondo prodotto dalla tua lista\n\n"
            "Usa /list per vedere i numeri dei tuoi prodotti.",
            parse_mode="Markdown",
        )
        return

    product_number_str = context.args[0]

    logger.info(f"User {user_id} requesting to delete product #{product_number_str}")

    try:
        # Parse product number
        try:
            product_number = int(product_number_str)
            if product_number < 1:
                raise ValueError("Product number must be positive")
        except ValueError:
            await update.message.reply_text(
                f"❌ Numero non valido: `{product_number_str}`\n\n"
                "Usa un numero intero positivo (es. 1, 2, 3...).\n"
                "Vedi /list per i numeri dei tuoi prodotti.",
                parse_mode="Markdown",
            )
            return

        # Get user's products
        products = await database.get_user_products(user_id)

        if not products:
            await update.message.reply_text(
                "📭 *Non hai prodotti da eliminare*\n\nUsa /add per aggiungere un prodotto!",
                parse_mode="Markdown",
            )
            return

        # Validate product number is in range
        if product_number > len(products):
            await update.message.reply_text(
                f"❌ Numero prodotto non valido: {product_number}\n\n"
                f"Hai solo {len(products)} prodotto/i monitorato/i.\n"
                "Usa /list per vedere la tua lista.",
            )
            return

        # Get product to delete (convert 1-based to 0-based index)
        product_to_delete = products[product_number - 1]
        product_id = product_to_delete["id"]
        asin = product_to_delete["asin"]

        # Delete product from database
        await database.delete_product(product_id)

        await update.message.reply_text(
            "✅ *Prodotto rimosso con successo!*\n\n"
            f"📦 ASIN: `{asin}`\n\n"
            "Il prodotto non sarà più monitorato.\n"
            "Usa /list per vedere i tuoi prodotti rimanenti.",
            parse_mode="Markdown",
        )

        logger.info(f"Product deleted for user {user_id}: id={product_id}, ASIN={asin}")

    except Exception as e:
        logger.error(f"Error in delete_handler for user {user_id}: {e}", exc_info=True)
        await update.message.reply_text("❌ Errore nell'eliminare il prodotto. Riprova più tardi.")
