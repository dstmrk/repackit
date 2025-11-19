"""Handler for /add command with conversational flow."""

import logging
import re
from datetime import date, timedelta

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

logger = logging.getLogger(__name__)

# Conversation states
WAITING_URL, WAITING_PRICE, WAITING_DEADLINE = range(3)


async def start_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Start the /add conversation flow.

    Step 1: Ask for Amazon product URL.
    """
    await update.message.reply_text(
        "📦 *Aggiungi un nuovo prodotto*\n\n"
        "Inviami il link del prodotto Amazon.it che hai acquistato.\n\n"
        "Esempio: `https://amazon.it/dp/B08N5WRWNW`\n\n"
        "Oppure scrivi /cancel per annullare.",
        parse_mode="Markdown",
    )
    return WAITING_URL


async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Handle URL input and validate it.

    Step 2: Validate URL is from Amazon.it, extract ASIN, then ask for price.
    """
    user_id = update.effective_user.id
    url = update.message.text.strip()

    # Validate it's an Amazon.it URL
    if not re.search(r"amazon\.it", url, re.IGNORECASE):
        await update.message.reply_text(
            "❌ *URL non valido*\n\n"
            "Il link deve essere di Amazon.it (non .com, .de, ecc.)\n\n"
            "Invia un link valido oppure /cancel per annullare.",
            parse_mode="Markdown",
        )
        return WAITING_URL

    # Extract ASIN from URL
    try:
        asin, marketplace = extract_asin(url)

        # Double check marketplace is "it"
        if marketplace != "it":
            await update.message.reply_text(
                "❌ *Marketplace non supportato*\n\n"
                "Al momento supportiamo solo Amazon.it\n\n"
                "Invia un link Amazon.it oppure /cancel per annullare.",
                parse_mode="Markdown",
            )
            return WAITING_URL

    except ValueError as e:
        await update.message.reply_text(
            f"❌ *URL Amazon non valido*\n\n"
            f"{e}\n\n"
            "Assicurati di usare un link Amazon corretto.\n\n"
            "Invia un link valido oppure /cancel per annullare.",
            parse_mode="Markdown",
        )
        return WAITING_URL

    # Store URL, ASIN, and marketplace in user_data
    context.user_data["product_url"] = url
    context.user_data["product_asin"] = asin
    context.user_data["product_marketplace"] = marketplace

    logger.info(f"User {user_id} provided valid URL: ASIN={asin}, marketplace={marketplace}")

    # Ask for price
    await update.message.reply_text(
        "✅ *Prodotto riconosciuto!*\n\n"
        f"📦 ASIN: `{asin}`\n\n"
        "Ora inviami il *prezzo che hai pagato* in euro.\n\n"
        "Esempio: `59.90` oppure `59,90`\n\n"
        "Oppure scrivi /cancel per annullare.",
        parse_mode="Markdown",
    )
    return WAITING_PRICE


async def handle_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Handle price input and validate it.

    Step 3: Validate price (number, max 16 digits total), then ask for deadline.
    """
    user_id = update.effective_user.id
    price_str = update.message.text.strip()

    # Parse price
    try:
        # Allow both comma and dot as decimal separator
        price_paid = float(price_str.replace(",", "."))

        # Validate price is positive
        if price_paid <= 0:
            await update.message.reply_text(
                "❌ *Prezzo non valido*\n\n"
                "Il prezzo deve essere un numero positivo.\n\n"
                "Esempio: `59.90` oppure `59,90`\n\n"
                "Riprova oppure /cancel per annullare.",
                parse_mode="Markdown",
            )
            return WAITING_PRICE

        # Validate max 16 digits total (including decimals)
        # Remove dots/commas and count digits
        digits_only = re.sub(r"[,.]", "", price_str)
        if len(digits_only) > 16:
            await update.message.reply_text(
                "❌ *Prezzo troppo lungo*\n\n"
                "Il prezzo può contenere al massimo 16 cifre in totale.\n\n"
                "Riprova oppure /cancel per annullare.",
                parse_mode="Markdown",
            )
            return WAITING_PRICE

    except ValueError:
        await update.message.reply_text(
            "❌ *Prezzo non valido*\n\n"
            f"Non riesco a interpretare `{price_str}` come un numero.\n\n"
            "Esempio: `59.90` oppure `59,90`\n\n"
            "Riprova oppure /cancel per annullare.",
            parse_mode="Markdown",
        )
        return WAITING_PRICE

    # Store price in user_data
    context.user_data["product_price"] = price_paid

    logger.info(f"User {user_id} provided valid price: €{price_paid:.2f}")

    # Ask for deadline
    await update.message.reply_text(
        "✅ *Prezzo salvato!*\n\n"
        f"💰 Prezzo: €{price_paid:.2f}\n\n"
        "Ora inviami la *scadenza del reso*.\n\n"
        "Puoi inviarmi:\n"
        "• Un numero di giorni (da 1 a 365)\n"
        "  Esempio: `30`\n\n"
        "• Una data nel formato gg-mm-aaaa\n"
        "  Esempio: `25-12-2024`\n\n"
        "Oppure scrivi /cancel per annullare.",
        parse_mode="Markdown",
    )
    return WAITING_DEADLINE


async def handle_deadline(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Handle deadline input, validate it, and save the product.

    Step 4: Validate deadline (days 1-365 or date gg-mm-aaaa), then save to database.
    """
    user_id = update.effective_user.id
    deadline_str = update.message.text.strip()

    # Parse deadline
    try:
        return_deadline = parse_deadline(deadline_str)
    except ValueError as e:
        await update.message.reply_text(
            f"❌ *Scadenza non valida*\n\n"
            f"{e}\n\n"
            "Invia:\n"
            "• Un numero di giorni (da 1 a 365), es. `30`\n"
            "• Una data nel formato gg-mm-aaaa, es. `25-12-2024`\n\n"
            "Riprova oppure /cancel per annullare.",
            parse_mode="Markdown",
        )
        return WAITING_DEADLINE

    # Check deadline is in the future
    if return_deadline < date.today():
        await update.message.reply_text(
            "❌ *La scadenza deve essere nel futuro!*\n\n"
            f"Data specificata: {return_deadline.strftime('%d/%m/%Y')}\n"
            f"Data odierna: {date.today().strftime('%d/%m/%Y')}\n\n"
            "Riprova oppure /cancel per annullare.",
            parse_mode="Markdown",
        )
        return WAITING_DEADLINE

    logger.info(f"User {user_id} provided valid deadline: {return_deadline}")

    # Retrieve stored data
    asin = context.user_data["product_asin"]
    marketplace = context.user_data["product_marketplace"]
    price_paid = context.user_data["product_price"]

    try:
        # Register user if not exists
        await database.add_user(user_id=user_id, language_code=update.effective_user.language_code)

        # Check product limit (max 10 products per user)
        user_products = await database.get_user_products(user_id)
        if len(user_products) >= 10:
            await update.message.reply_text(
                "❌ *Limite prodotti raggiunto!*\n\n"
                "Puoi monitorare al massimo *10 prodotti* contemporaneamente.\n\n"
                "Usa `/delete <numero>` per rimuovere un prodotto e fare spazio.",
                parse_mode="Markdown",
            )
            logger.info(f"User {user_id} reached product limit (10 products)")
            # Clear user_data and end conversation
            context.user_data.clear()
            return ConversationHandler.END

        # Add product to database
        await database.add_product(
            user_id=user_id,
            asin=asin,
            marketplace=marketplace,
            price_paid=price_paid,
            return_deadline=return_deadline,
            min_savings_threshold=None,  # Not asked in conversational flow
        )

        # Build success message
        days_remaining = (return_deadline - date.today()).days
        message = (
            "✅ *Prodotto aggiunto con successo!*\n\n"
            f"📦 ASIN: `{asin}`\n"
            f"🌍 Marketplace: amazon.{marketplace}\n"
            f"💰 Prezzo pagato: €{price_paid:.2f}\n"
            f"📅 Scadenza reso: {return_deadline.strftime('%d/%m/%Y')} (tra {days_remaining} giorni)\n\n"
            "_Monitorerò il prezzo ogni giorno e ti avviserò se scende!_\n\n"
            "Usa /list per vedere tutti i tuoi prodotti."
        )

        await update.message.reply_text(message, parse_mode="Markdown")

        logger.info(
            f"Product added for user {user_id}: ASIN={asin}, price={price_paid}, deadline={return_deadline}"
        )

    except Exception as e:
        logger.error(f"Error in handle_deadline for user {user_id}: {e}", exc_info=True)
        await update.message.reply_text("❌ Errore nell'aggiungere il prodotto. Riprova più tardi.")

    # Clear user_data and end conversation
    context.user_data.clear()
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Cancel the conversation.
    """
    await update.message.reply_text(
        "❌ *Operazione annullata*\n\n"
        "Nessun prodotto è stato aggiunto.\n\n"
        "Usa /add per iniziare di nuovo.",
        parse_mode="Markdown",
    )

    # Clear user_data
    context.user_data.clear()
    return ConversationHandler.END


def parse_deadline(deadline_input: str) -> date:
    """
    Parse return deadline from user input.

    Supports three formats:
    - Number of days (1-365): "30" -> 30 days from today
    - Date format gg-mm-aaaa: "25-12-2024" -> specific date
    - Date format yyyy-mm-dd (ISO): "2024-12-25" -> specific date (for /update compatibility)

    Args:
        deadline_input: User input string

    Returns:
        Return deadline as date object

    Raises:
        ValueError: If input format is invalid
    """
    # Try parsing as number of days
    try:
        days = int(deadline_input)

        # Validate range 1-365
        if days < 1 or days > 365:
            raise ValueError("Il numero di giorni deve essere tra 1 e 365")

        return date.today() + timedelta(days=days)

    except ValueError as e:
        # If it's our custom error, re-raise it
        if "giorni deve essere" in str(e):
            raise
        # Otherwise, continue to try date parsing

    # Try parsing as date in format gg-mm-aaaa or yyyy-mm-dd
    try:
        parts = deadline_input.split("-")
        if len(parts) != 3:
            raise ValueError("Invalid date format")

        # Determine format by checking which part is the year (4 digits)
        if len(parts[0]) == 4:
            # Format: yyyy-mm-dd (ISO format)
            year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
        elif len(parts[2]) == 4:
            # Format: gg-mm-aaaa
            day, month, year = int(parts[0]), int(parts[1]), int(parts[2])
        else:
            raise ValueError("Year must be 4 digits")

        return date(year, month, day)

    except (ValueError, AttributeError):
        raise ValueError(
            "Formato non valido. Usa giorni (es. `30`) o data gg-mm-aaaa (es. `25-12-2024`)"
        ) from None


# Create the ConversationHandler
add_conversation_handler = ConversationHandler(
    entry_points=[CommandHandler("add", start_add)],
    states={
        WAITING_URL: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url)],
        WAITING_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_price)],
        WAITING_DEADLINE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_deadline)],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
)
