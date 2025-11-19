"""Handler for /delete command with confirmation."""

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

import database

logger = logging.getLogger(__name__)


async def delete_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle /delete command.

    Shows product details and asks for confirmation with inline buttons.

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
        price_paid = product_to_delete["price_paid"]
        return_deadline = product_to_delete["return_deadline"]
        marketplace = product_to_delete.get("marketplace", "it")

        # Format deadline
        from datetime import date

        deadline_date = date.fromisoformat(return_deadline)
        deadline_str = deadline_date.strftime("%d/%m/%Y")

        # Create inline keyboard with confirmation buttons
        keyboard = [
            [
                InlineKeyboardButton(
                    "✅ Sì, elimina", callback_data=f"delete_confirm_{product_id}"
                ),
                InlineKeyboardButton("❌ No, annulla", callback_data=f"delete_cancel_{product_id}"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        # Show confirmation message with product details
        confirmation_message = (
            "⚠️ *Sei sicuro di voler eliminare questo prodotto?*\n\n"
            f"📦 ASIN: `{asin}`\n"
            f"🌍 Marketplace: amazon.{marketplace}\n"
            f"💰 Prezzo pagato: €{price_paid:.2f}\n"
            f"📅 Scadenza reso: {deadline_str}\n\n"
            "_Il prodotto non sarà più monitorato._"
        )

        await update.message.reply_text(
            confirmation_message, parse_mode="Markdown", reply_markup=reply_markup
        )

        logger.info(
            f"Confirmation requested for user {user_id}: product_id={product_id}, ASIN={asin}"
        )

    except Exception as e:
        logger.error(f"Error in delete_handler for user {user_id}: {e}", exc_info=True)
        await update.message.reply_text("❌ Errore nel processare la richiesta. Riprova più tardi.")


async def delete_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle callback queries from delete confirmation buttons.

    Args:
        update: Telegram update object
        context: Telegram context object
    """
    query = update.callback_query
    user_id = update.effective_user.id

    # Answer callback query to remove loading state
    await query.answer()

    callback_data = query.data

    try:
        # Parse callback data
        if callback_data.startswith("delete_confirm_"):
            # Extract product_id from callback data
            product_id = int(callback_data.replace("delete_confirm_", ""))

            logger.info(f"User {user_id} confirmed deletion of product_id={product_id}")

            # Get product details before deleting (for confirmation message)
            products = await database.get_user_products(user_id)
            product_to_delete = next((p for p in products if p["id"] == product_id), None)

            if product_to_delete is None:
                await query.edit_message_text(
                    "❌ Prodotto non trovato. Potrebbe essere già stato eliminato."
                )
                return

            asin = product_to_delete["asin"]

            # Delete product from database
            await database.delete_product(product_id)

            # Edit message to show success
            success_message = (
                "✅ *Prodotto eliminato con successo!*\n\n"
                f"📦 ASIN: `{asin}`\n\n"
                "Il prodotto non sarà più monitorato.\n"
                "Usa /list per vedere i tuoi prodotti rimanenti."
            )

            await query.edit_message_text(success_message, parse_mode="Markdown")

            logger.info(f"Product deleted for user {user_id}: id={product_id}, ASIN={asin}")

        elif callback_data.startswith("delete_cancel_"):
            # Extract product_id from callback data
            product_id = int(callback_data.replace("delete_cancel_", ""))

            logger.info(f"User {user_id} cancelled deletion of product_id={product_id}")

            # Edit message to show cancellation
            await query.edit_message_text(
                "❌ *Operazione annullata*\n\nIl prodotto non è stato eliminato.",
                parse_mode="Markdown",
            )

    except Exception as e:
        logger.error(f"Error in delete_callback_handler for user {user_id}: {e}", exc_info=True)
        await query.edit_message_text("❌ Errore nell'elaborare la risposta. Riprova più tardi.")


# Create handlers
delete_command_handler = CommandHandler("delete", delete_handler)
delete_callback_query_handler = CallbackQueryHandler(
    delete_callback_handler, pattern="^delete_(confirm|cancel)_"
)
