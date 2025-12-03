"""Handler for /list command."""

import logging
from datetime import UTC, date, datetime

from telegram import Update
from telegram.ext import ContextTypes

import database
from data_reader import build_affiliate_url

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
                "📭 <b>Nessun prodotto monitorato</b>\n\n"
                "Usa /add per aggiungere il tuo primo prodotto!",
                parse_mode="HTML",
            )
            return

        # Build product list message
        message_parts = ["📦 <b>I tuoi prodotti monitorati:</b>\n"]

        today = datetime.now(UTC).date()

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
                deadline_info = f"{deadline_str} (<b>oggi!</b>)"
            else:
                deadline_info = f"{deadline_str} (<b>scaduto</b>)"

            # Build product URL
            product_url = build_affiliate_url(asin, marketplace)

            # Add product info
            product_info = (
                f"\n<b>{idx}.</b> <a href='{product_url}'>{product_name}</a>\n"
                f"   💰 Prezzo pagato: €{price_paid:.2f}\n"
                f"   📅 Scadenza reso: {deadline_info}\n"
            )

            if min_savings > 0:
                product_info += f"   🎯 Risparmio minimo: €{min_savings:.2f}\n"

            message_parts.append(product_info)

        message = "".join(message_parts)

        # Add footer with dynamic limit
        user_limit = await database.get_user_product_limit(user_id)
        message += (
            f"\n<i>Hai {len(products)}/{user_limit} prodotti monitorati.</i>\n"
            f"Usa /delete per rimuoverne uno, /update per modificarne uno."
        )

        # Show /share hint if user is running low on slots
        slots_available = user_limit - len(products)
        max_slots = database.DEFAULT_MAX_PRODUCTS
        if user_limit < max_slots and slots_available < 3:
            message += (
                "\n\n💡 <b>Suggerimento:</b> Stai esaurendo gli slot! "
                "Usa /share per invitare amici e guadagnare più spazio."
            )

        await update.message.reply_text(message, parse_mode="HTML", disable_web_page_preview=True)

    except Exception as e:
        logger.error(f"Error in list_handler for user {user_id}: {e}", exc_info=True)
        await update.message.reply_text(
            "❌ Errore nel recuperare i tuoi prodotti. Riprova più tardi."
        )
