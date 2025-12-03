"""Handler for /delete command with button-based product selection."""

import html
import logging
from datetime import date

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

import database

logger = logging.getLogger(__name__)


async def start_delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Start the /delete flow.

    Shows list of products with inline buttons for selection.

    Args:
        update: Telegram update object
        context: Telegram context object
    """
    user_id = update.effective_user.id

    logger.info(f"User {user_id} started /delete flow")

    try:
        # Get user's products
        products = await database.get_user_products(user_id)

        if not products:
            await update.message.reply_text(
                "📭 <b>Non hai prodotti da eliminare</b>\n\nUsa /add per aggiungere un prodotto!",
                parse_mode="HTML",
            )
            return

        # Build keyboard with product buttons
        keyboard = []
        for idx, product in enumerate(products, start=1):
            product_id = product["id"]
            product_name = product.get("product_name") or f"Prodotto #{idx}"
            price_paid = product["price_paid"]

            # Button text shows name and price
            button_text = f"{idx}. {product_name} - €{price_paid:.2f}"
            keyboard.append(
                [InlineKeyboardButton(button_text, callback_data=f"delete_select_{product_id}")]
            )

        # Add cancel button
        keyboard.append([InlineKeyboardButton("❌ Annulla", callback_data="delete_cancel_main")])

        reply_markup = InlineKeyboardMarkup(keyboard)

        message = (
            "🗑️ <b>Elimina un prodotto</b>\n\n"
            "Seleziona il prodotto che vuoi rimuovere dal monitoraggio:"
        )

        await update.message.reply_text(message, parse_mode="HTML", reply_markup=reply_markup)

    except Exception as e:
        logger.error(f"Error in start_delete for user {user_id}: {e}", exc_info=True)
        await update.message.reply_text("❌ Errore nel processare la richiesta. Riprova più tardi.")


async def delete_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle callback queries from delete buttons.

    Handles:
    - Product selection (delete_select_{id})
    - Confirmation (delete_confirm_{id})
    - Cancellation (delete_cancel_{id} or delete_cancel_main)

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
        # Handle product selection
        if callback_data.startswith("delete_select_"):
            product_id = int(callback_data.replace("delete_select_", ""))

            logger.info(f"User {user_id} selected product_id={product_id} for deletion")

            # Get product details
            products = await database.get_user_products(user_id)
            product = next((p for p in products if p["id"] == product_id), None)

            if product is None:
                await query.edit_message_text(
                    "❌ Prodotto non trovato. Potrebbe essere già stato eliminato."
                )
                return

            product_name = product.get("product_name") or "Prodotto senza nome"
            asin = product["asin"]
            price_paid = product["price_paid"]
            return_deadline = date.fromisoformat(product["return_deadline"])
            deadline_str = return_deadline.strftime("%d/%m/%Y")
            min_savings = product["min_savings_threshold"] or 0

            # Create confirmation keyboard
            keyboard = [
                [
                    InlineKeyboardButton(
                        "✅ Sì, elimina", callback_data=f"delete_confirm_{product_id}"
                    ),
                    InlineKeyboardButton(
                        "❌ No, annulla", callback_data=f"delete_cancel_{product_id}"
                    ),
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            # Show confirmation message with product details
            confirmation_message = (
                "⚠️ <b>Sei sicuro di voler eliminare questo prodotto?</b>\n\n"
                f"📦 <b>{html.escape(product_name)}</b>\n"
                f"🔖 ASIN: <code>{asin}</code>\n"
                f"💰 Prezzo pagato: €{price_paid:.2f}\n"
                f"📅 Scadenza reso: {deadline_str}\n"
            )

            if min_savings > 0:
                confirmation_message += f"🎯 Risparmio minimo: €{min_savings:.2f}\n"

            confirmation_message += "\n<i>Il prodotto non sarà più monitorato.</i>"

            await query.edit_message_text(
                confirmation_message, parse_mode="HTML", reply_markup=reply_markup
            )

        # Handle confirmation
        elif callback_data.startswith("delete_confirm_"):
            product_id = int(callback_data.replace("delete_confirm_", ""))

            logger.info(f"User {user_id} confirmed deletion of product_id={product_id}")

            # Get product details before deleting (for confirmation message)
            products = await database.get_user_products(user_id)
            product = next((p for p in products if p["id"] == product_id), None)

            if product is None:
                await query.edit_message_text(
                    "❌ Prodotto non trovato. Potrebbe essere già stato eliminato."
                )
                return

            product_name = product.get("product_name") or "Prodotto"

            # Delete product from database
            await database.delete_product(product_id)

            # Edit message to show success
            success_message = (
                "✅ <b>Prodotto eliminato con successo!</b>\n\n"
                f"📦 <b>{html.escape(product_name)}</b>\n\n"
                "Il prodotto non sarà più monitorato.\n"
                "Usa /list per vedere i tuoi prodotti rimanenti."
            )

            await query.edit_message_text(success_message, parse_mode="HTML")

            logger.info(f"Product deleted for user {user_id}: id={product_id}, name={product_name}")

        # Handle cancellation
        elif callback_data.startswith("delete_cancel_"):
            logger.info(f"User {user_id} cancelled deletion")

            # Edit message to show cancellation
            await query.edit_message_text(
                "❌ <b>Operazione annullata</b>\n\nNessun prodotto è stato eliminato.",
                parse_mode="HTML",
            )

    except Exception as e:
        logger.error(f"Error in delete_callback_handler for user {user_id}: {e}", exc_info=True)
        await query.edit_message_text("❌ Errore nell'elaborare la risposta. Riprova più tardi.")


# Create handlers
delete_command_handler = CommandHandler("delete", start_delete)
delete_callback_query_handler = CallbackQueryHandler(
    delete_callback_handler, pattern="^delete_(select|confirm|cancel)_"
)
