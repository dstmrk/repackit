"""Handler for /list command."""

import logging
from datetime import date

from telegram import Update
from telegram.ext import ContextTypes

import database
from data_reader import build_affiliate_url
from handlers.add import MAX_PRODUCTS_PER_USER

logger = logging.getLogger(__name__)


async def list_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle /list command.

    Shows user's monitored products with 1-based indexing.

    Args:
        update: Telegram update object
        context: Telegram context object
    """
    user_id = update.effective_user.id

    logger.info(f"User {user_id} requested product list")

    try:
        # Get user's products
        products = await database.get_user_products(user_id)

        if not products:
            await update.message.reply_text(
                "📭 *Nessun prodotto monitorato*\n\n"
                "Usa /add per aggiungere il tuo primo prodotto!",
                parse_mode="Markdown",
            )
            return

        # Build product list message
        message_parts = ["📦 *I tuoi prodotti monitorati:*\n"]

        today = date.today()

        for idx, product in enumerate(products, start=1):
            product_name = product.get("product_name") or "Prodotto senza nome"
            asin = product["asin"]
            price_paid = product["price_paid"]
            return_deadline = date.fromisoformat(product["return_deadline"])
            min_savings = product["min_savings_threshold"] or 0
            marketplace = product.get("marketplace", "it")

            # Calculate days remaining
            days_remaining = (return_deadline - today).days

            # Format deadline info
            deadline_str = return_deadline.strftime("%d/%m/%Y")
            if days_remaining > 0:
                deadline_info = f"{deadline_str} (tra {days_remaining} giorni)"
            elif days_remaining == 0:
                deadline_info = f"{deadline_str} (*oggi!*)"
            else:
                deadline_info = f"{deadline_str} (*scaduto*)"

            # Build product URL
            product_url = build_affiliate_url(asin, marketplace)

            # Add product info
            product_info = (
                f"\n*{idx}.* [{product_name}]({product_url})\n"
                f"   💰 Prezzo pagato: €{price_paid:.2f}\n"
                f"   📅 Scadenza reso: {deadline_info}\n"
            )

            if min_savings > 0:
                product_info += f"   🎯 Risparmio minimo: €{min_savings:.2f}\n"

            message_parts.append(product_info)

        message = "".join(message_parts)

        # Add footer
        message += (
            f"\n_Hai {len(products)}/{MAX_PRODUCTS_PER_USER} prodotti monitorati._\n"
            f"Usa /delete per rimuoverne uno, /update per modificarne uno."
        )

        await update.message.reply_text(
            message, parse_mode="Markdown", disable_web_page_preview=True
        )

    except Exception as e:
        logger.error(f"Error in list_handler for user {user_id}: {e}", exc_info=True)
        await update.message.reply_text(
            "❌ Errore nel recuperare i tuoi prodotti. Riprova più tardi."
        )
