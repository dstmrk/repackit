"""Handler for /add command with conversational flow."""

import html
import logging
import re
from datetime import UTC, date, datetime

import aiosqlite
from telegram import Update
from telegram.ext import (
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

import database
from data_reader import extract_asin
from handlers import validators

logger = logging.getLogger(__name__)

# Conversation states
WAITING_PRODUCT_NAME, WAITING_URL, WAITING_PRICE, WAITING_DEADLINE, WAITING_MIN_SAVINGS = range(5)


async def start_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Start the /add conversation flow.

    Step 1: Ask for product name.
    """
    await update.message.reply_text(
        "📦 <b>Aggiungi un nuovo prodotto</b>\n\n"
        "Come vuoi chiamare questo prodotto?\n\n"
        "Esempio: <code>iPhone 15 Pro</code> oppure <code>Cuffie Sony</code>\n\n"
        "Questo nome ti aiuterà a riconoscere il prodotto nella lista.\n\n"
        "Oppure scrivi /cancel per annullare.",
        parse_mode="HTML",
    )
    return WAITING_PRODUCT_NAME


async def handle_product_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Handle product name input and validate it.

    Step 2: Store product name, then ask for URL.
    """
    user_id = update.effective_user.id
    product_name_input = update.message.text

    # Validate product name using shared validator
    is_valid, product_name, error_msg = validators.validate_product_name(product_name_input)

    if not is_valid:
        await update.message.reply_text(error_msg, parse_mode="HTML")
        return WAITING_PRODUCT_NAME

    # Store product name
    context.user_data["product_name"] = product_name

    logger.info(f"User {user_id} provided product name: {product_name}")

    # Ask for URL
    await update.message.reply_text(
        "✅ <b>Nome salvato!</b>\n\n"
        f"📦 {product_name}\n\n"
        "Ora inviami il <b>link del prodotto Amazon.it</b> che hai acquistato.\n\n"
        "Esempio: <code>https://amazon.it/dp/B08N5WRWNW</code>\n\n"
        "Oppure scrivi /cancel per annullare.",
        parse_mode="HTML",
    )
    return WAITING_URL


async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Handle URL input and validate it.

    Step 3: Validate URL is from Amazon.it, extract ASIN, then ask for price.
    """
    user_id = update.effective_user.id
    url = update.message.text.strip()

    # Validate it's an Amazon.it URL
    if not re.search(r"amazon\.it", url, re.IGNORECASE):
        await update.message.reply_text(
            "❌ <b>URL non valido</b>\n\n"
            "Il link deve essere di Amazon.it (non .com, .de, ecc.)\n\n"
            "Invia un link valido oppure /cancel per annullare.",
            parse_mode="HTML",
        )
        return WAITING_URL

    # Extract ASIN from URL
    try:
        asin, marketplace = extract_asin(url)

        # Double check marketplace is "it"
        if marketplace != "it":
            await update.message.reply_text(
                "❌ <b>Marketplace non supportato</b>\n\n"
                "Al momento supportiamo solo Amazon.it\n\n"
                "Invia un link Amazon.it oppure /cancel per annullare.",
                parse_mode="HTML",
            )
            return WAITING_URL

    except ValueError as e:
        await update.message.reply_text(
            f"❌ <b>URL Amazon non valido</b>\n\n"
            f"{e}\n\n"
            "Assicurati di usare un link Amazon corretto.\n\n"
            "Invia un link valido oppure /cancel per annullare.",
            parse_mode="HTML",
        )
        return WAITING_URL

    # Store URL, ASIN, and marketplace in user_data
    context.user_data["product_url"] = url
    context.user_data["product_asin"] = asin
    context.user_data["product_marketplace"] = marketplace

    logger.info(f"User {user_id} provided valid URL: ASIN={asin}, marketplace={marketplace}")

    # Ask for price
    await update.message.reply_text(
        "✅ <b>Prodotto riconosciuto!</b>\n\n"
        f"📦 ASIN: <code>{asin}</code>\n\n"
        "Ora inviami il <b>prezzo che hai pagato</b> in euro.\n\n"
        "Esempio: <code>59.90</code> oppure <code>59,90</code>\n\n"
        "Oppure scrivi /cancel per annullare.",
        parse_mode="HTML",
    )
    return WAITING_PRICE


async def handle_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Handle price input and validate it.

    Step 4: Validate price (number, max 16 digits total), then ask for deadline.
    """
    user_id = update.effective_user.id
    price_input = update.message.text

    # Validate price using shared validator
    is_valid, price_paid, error_msg = validators.validate_price(price_input, max_digits=16)

    if not is_valid:
        await update.message.reply_text(error_msg, parse_mode="HTML")
        return WAITING_PRICE

    # Store price in user_data
    context.user_data["product_price"] = price_paid

    logger.info(f"User {user_id} provided valid price: €{price_paid:.2f}")

    # Ask for deadline
    await update.message.reply_text(
        "✅ <b>Prezzo salvato!</b>\n\n"
        f"💰 Prezzo: €{price_paid:.2f}\n\n"
        "Ora inviami la <b>scadenza del reso</b>.\n\n"
        "Puoi inviarmi:\n"
        "• Un numero di giorni (da 1 a 365)\n"
        "  Esempio: <code>30</code>\n\n"
        "• Una data nel formato gg-mm-aaaa\n"
        "  Esempio: <code>09-05-2025</code>\n\n"
        "Oppure scrivi /cancel per annullare.",
        parse_mode="HTML",
    )
    return WAITING_DEADLINE


async def handle_deadline(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Handle deadline input and validate it.

    Step 5: Validate deadline (days 1-365 or date gg-mm-aaaa), then ask for min savings.
    """
    user_id = update.effective_user.id
    deadline_input = update.message.text

    # Parse deadline using shared validator
    try:
        return_deadline = validators.parse_deadline(deadline_input)
    except ValueError as e:
        await update.message.reply_text(
            f"❌ <b>Scadenza non valida</b>\n\n"
            f"{e}\n\n"
            "Invia:\n"
            "• Un numero di giorni (da 1 a 365), es. <code>30</code>\n"
            "• Una data nel formato gg-mm-aaaa, es. <code>09-05-2025</code>\n\n"
            "Riprova oppure /cancel per annullare.",
            parse_mode="HTML",
        )
        return WAITING_DEADLINE

    # Store deadline
    context.user_data["product_deadline"] = return_deadline

    logger.info(f"User {user_id} provided valid deadline: {return_deadline}")

    # Ask for minimum savings threshold
    price_paid = context.user_data["product_price"]
    await update.message.reply_text(
        "✅ <b>Scadenza salvata!</b>\n\n"
        f"📅 Scadenza: {return_deadline.strftime('%d/%m/%Y')}\n\n"
        "Infine, qual è il <b>risparmio minimo</b> per cui vuoi essere notificato?\n\n"
        "Invia un numero in euro (ad esempio <code>5</code> per essere avvisato solo se risparmi almeno €5).\n\n"
        f"Scrivi <code>0</code> per essere notificato di <b>qualunque</b> prezzo migliore di €{price_paid:.2f}.\n\n"
        "Oppure scrivi /cancel per annullare.",
        parse_mode="HTML",
    )
    return WAITING_MIN_SAVINGS


async def _process_first_product_referral_bonus(
    user_id: int, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Process referral bonus for user's first product addition.

    If this is the user's first product and they were referred,
    give bonus slots to the referrer.

    Args:
        user_id: User who added their first product
        context: Telegram context (for sending notification)
    """
    user = await database.get_user(user_id)
    if not user or not user["referred_by"] or user["referral_bonus_given"]:
        return

    referrer_id = user["referred_by"]

    # Verify referrer still exists
    referrer = await database.get_user(referrer_id)
    if not referrer:
        return

    current_limit = await database.get_user_product_limit(referrer_id)

    # Only give bonus if referrer is not already at cap
    if current_limit < database.DEFAULT_MAX_PRODUCTS:
        new_limit = await database.increment_user_product_limit(
            referrer_id, database.PRODUCTS_PER_REFERRAL
        )

        # Mark bonus as given
        await database.mark_referral_bonus_given(user_id)

        # Notify referrer
        try:
            await context.bot.send_message(
                chat_id=referrer_id,
                text=(
                    "🎉 <b>Un amico che hai invitato ha aggiunto il suo primo prodotto!</b>\n\n"
                    f"💎 Hai ricevuto +3 slot (ora ne hai {new_limit}/{database.DEFAULT_MAX_PRODUCTS})"
                ),
                parse_mode="HTML",
            )
            logger.info(
                f"Referral bonus given: user {user_id} → referrer {referrer_id} "
                f"(+{database.PRODUCTS_PER_REFERRAL} slots, now {new_limit})"
            )
        except Exception as e:
            logger.warning(f"Could not notify referrer {referrer_id}: {e}")
    else:
        # Referrer already at cap, mark bonus as given anyway
        await database.mark_referral_bonus_given(user_id)
        logger.info(
            f"User {user_id} first product added but referrer {referrer_id} " "already at max limit"
        )


def _build_product_success_message(
    product_name: str,
    asin: str,
    price_paid: float,
    return_deadline: date,
    min_savings: float,
) -> str:
    """
    Build success message for product addition.

    Args:
        product_name: User-defined product name
        asin: Amazon Standard Identification Number
        price_paid: Price user paid
        return_deadline: Return deadline date
        min_savings: Minimum savings threshold

    Returns:
        Formatted success message (HTML)
    """
    days_remaining = (return_deadline - datetime.now(UTC).date()).days
    message = (
        "✅ <b>Prodotto aggiunto con successo!</b>\n\n"
        f"📦 <b>{html.escape(product_name)}</b>\n"
        f"🔖 ASIN: <code>{asin}</code>\n"
        f"💰 Prezzo pagato: €{price_paid:.2f}\n"
        f"📅 Scadenza reso: {return_deadline.strftime('%d/%m/%Y')} (tra {days_remaining} giorni)\n"
    )

    if min_savings > 0:
        message += f"🎯 Risparmio minimo: €{min_savings:.2f}\n"
    else:
        message += "🎯 Notifica per qualsiasi risparmio\n"

    message += (
        "\n<i>Monitorerò il prezzo ogni giorno e ti avviserò se scende!</i>\n\n"
        "Usa /list per vedere tutti i tuoi prodotti."
    )

    return message


async def handle_min_savings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Handle minimum savings threshold input and save the product.

    Step 6: Validate min savings, then save to database.
    """
    user_id = update.effective_user.id
    threshold_input = update.message.text

    # Get price_paid from context for validation
    price_paid = context.user_data["product_price"]

    # Validate threshold using shared validator
    is_valid, min_savings, error_msg = validators.validate_threshold(
        threshold_input, max_value=price_paid
    )

    if not is_valid:
        await update.message.reply_text(error_msg, parse_mode="HTML")
        return WAITING_MIN_SAVINGS

    logger.info(f"User {user_id} provided min savings: €{min_savings:.2f}")

    # Retrieve stored data
    product_name = context.user_data["product_name"]
    asin = context.user_data["product_asin"]
    marketplace = context.user_data["product_marketplace"]
    price_paid = context.user_data["product_price"]
    return_deadline = context.user_data["product_deadline"]

    try:
        # Register user if not exists
        await database.add_user(user_id=user_id, language_code=update.effective_user.language_code)

        # Check product limit (dynamic per-user limit)
        user_products = await database.get_user_products(user_id)
        user_limit = await database.get_user_product_limit(user_id)

        if len(user_products) >= user_limit:
            await update.message.reply_text(
                "❌ <b>Limite prodotti raggiunto!</b>\n\n"
                f"Puoi monitorare al massimo <b>{user_limit} prodotti</b> contemporaneamente.\n\n"
                "Usa /delete per rimuovere un prodotto e fare spazio.",
                parse_mode="HTML",
            )
            logger.info(f"User {user_id} reached product limit ({user_limit} products)")
            # Clear user_data and end conversation
            context.user_data.clear()
            return ConversationHandler.END

        # Add product to database with atomic first-product check
        # This prevents race conditions where multiple concurrent requests
        # could both trigger referral bonuses
        _, is_first_product = await database.add_product_atomic(
            user_id=user_id,
            product_name=product_name,
            asin=asin,
            marketplace=marketplace,
            price_paid=price_paid,
            return_deadline=return_deadline,
            min_savings_threshold=min_savings,
        )

        # Increment promotional metric: total products registered
        await database.increment_metric("products_total_count")

        # If this was the first product, give referral bonus to inviter
        # The is_first_product flag comes from atomic transaction, so it's safe
        if is_first_product:
            await _process_first_product_referral_bonus(user_id, context)

        # Build and send success message
        message = _build_product_success_message(
            product_name, asin, price_paid, return_deadline, min_savings
        )
        await update.message.reply_text(message, parse_mode="HTML")

        # Show /share hint if user is running low on slots (same logic as /list)
        # Note: user_products was fetched before insert, so add 1 for the new product
        current_product_count = len(user_products) + 1
        slots_available = user_limit - current_product_count
        max_slots = database.DEFAULT_MAX_PRODUCTS
        if user_limit < max_slots and slots_available < 3:
            hint_message = (
                f"<i>Hai {current_product_count}/{user_limit} prodotti monitorati.</i>\n\n"
                "💡 <b>Suggerimento:</b> Stai esaurendo gli slot! "
                "Usa /share per invitare amici e guadagnare più spazio."
            )
            await update.message.reply_text(hint_message, parse_mode="HTML")

        logger.info(
            f"Product added for user {user_id}: name={product_name}, ASIN={asin}, "
            f"price={price_paid}, deadline={return_deadline}, min_savings={min_savings}"
        )

    except aiosqlite.IntegrityError as e:
        # Database trigger enforces product limit
        if "Product limit exceeded" in str(e):
            await update.message.reply_text(
                "❌ <b>Limite prodotti raggiunto!</b>\n\n"
                f"Puoi monitorare al massimo <b>{user_limit} prodotti</b> contemporaneamente.\n\n"
                "Usa /delete per rimuovere un prodotto e fare spazio.",
                parse_mode="HTML",
            )
            logger.info(
                f"User {user_id} hit product limit (database trigger): {user_limit} products"
            )
        else:
            # Other integrity errors
            logger.error(f"Database integrity error for user {user_id}: {e}", exc_info=True)
            await update.message.reply_text(
                "❌ Errore nell'aggiungere il prodotto. Riprova più tardi."
            )
    except Exception as e:
        logger.error(f"Error in handle_min_savings for user {user_id}: {e}", exc_info=True)
        await update.message.reply_text("❌ Errore nell'aggiungere il prodotto. Riprova più tardi.")

    # Clear user_data and end conversation
    context.user_data.clear()
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Cancel the conversation.
    """
    await update.message.reply_text(
        "❌ <b>Operazione annullata</b>\n\n"
        "Nessun prodotto è stato aggiunto.\n\n"
        "Usa /add per iniziare di nuovo.",
        parse_mode="HTML",
    )

    # Clear user_data
    context.user_data.clear()
    return ConversationHandler.END


# Create the ConversationHandler
add_conversation_handler = ConversationHandler(
    entry_points=[CommandHandler("add", start_add)],
    states={
        WAITING_PRODUCT_NAME: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_product_name)
        ],
        WAITING_URL: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url)],
        WAITING_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_price)],
        WAITING_DEADLINE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_deadline)],
        WAITING_MIN_SAVINGS: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_min_savings)],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
)
