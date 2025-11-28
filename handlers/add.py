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
WAITING_PRODUCT_NAME, WAITING_URL, WAITING_PRICE, WAITING_DEADLINE, WAITING_MIN_SAVINGS = range(5)


async def start_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Start the /add conversation flow.

    Step 1: Ask for product name.
    """
    await update.message.reply_text(
        "📦 *Aggiungi un nuovo prodotto*\n\n"
        "Come vuoi chiamare questo prodotto?\n\n"
        "Esempio: `iPhone 15 Pro` oppure `Cuffie Sony`\n\n"
        "Questo nome ti aiuterà a riconoscere il prodotto nella lista.\n\n"
        "Oppure scrivi /cancel per annullare.",
        parse_mode="Markdown",
    )
    return WAITING_PRODUCT_NAME


async def handle_product_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Handle product name input and validate it.

    Step 2: Store product name, then ask for URL.
    """
    user_id = update.effective_user.id
    product_name = update.message.text.strip()

    # Validate length (between 3 and 100 characters)
    if len(product_name) < 3:
        await update.message.reply_text(
            "❌ *Nome troppo corto*\n\n"
            "Il nome del prodotto deve contenere almeno 3 caratteri.\n\n"
            "Riprova oppure /cancel per annullare.",
            parse_mode="Markdown",
        )
        return WAITING_PRODUCT_NAME

    if len(product_name) > 100:
        await update.message.reply_text(
            "❌ *Nome troppo lungo*\n\n"
            "Il nome del prodotto può contenere al massimo 100 caratteri.\n\n"
            "Riprova oppure /cancel per annullare.",
            parse_mode="Markdown",
        )
        return WAITING_PRODUCT_NAME

    # Store product name
    context.user_data["product_name"] = product_name

    logger.info(f"User {user_id} provided product name: {product_name}")

    # Ask for URL
    await update.message.reply_text(
        "✅ *Nome salvato!*\n\n"
        f"📦 {product_name}\n\n"
        "Ora inviami il *link del prodotto Amazon.it* che hai acquistato.\n\n"
        "Esempio: `https://amazon.it/dp/B08N5WRWNW`\n\n"
        "Oppure scrivi /cancel per annullare.",
        parse_mode="Markdown",
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

    Step 4: Validate price (number, max 16 digits total), then ask for deadline.
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
        "  Esempio: `09-05-2025`\n\n"
        "Oppure scrivi /cancel per annullare.",
        parse_mode="Markdown",
    )
    return WAITING_DEADLINE


async def handle_deadline(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Handle deadline input and validate it.

    Step 5: Validate deadline (days 1-365 or date gg-mm-aaaa), then ask for min savings.
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
            "• Una data nel formato gg-mm-aaaa, es. `09-05-2025`\n\n"
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

    # Store deadline
    context.user_data["product_deadline"] = return_deadline

    logger.info(f"User {user_id} provided valid deadline: {return_deadline}")

    # Ask for minimum savings threshold
    price_paid = context.user_data["product_price"]
    await update.message.reply_text(
        "✅ *Scadenza salvata!*\n\n"
        f"📅 Scadenza: {return_deadline.strftime('%d/%m/%Y')}\n\n"
        "Infine, qual è il *risparmio minimo* per cui vuoi essere notificato?\n\n"
        "Invia un numero in euro (ad esempio `5` per essere avvisato solo se risparmi almeno €5).\n\n"
        f"Scrivi `0` per essere notificato di *qualunque* prezzo migliore di €{price_paid:.2f}.\n\n"
        "Oppure scrivi /cancel per annullare.",
        parse_mode="Markdown",
    )
    return WAITING_MIN_SAVINGS


async def handle_min_savings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Handle minimum savings threshold input and save the product.

    Step 6: Validate min savings, then save to database.
    """
    user_id = update.effective_user.id
    savings_str = update.message.text.strip()

    # Parse min savings
    try:
        # Allow both comma and dot as decimal separator
        min_savings = float(savings_str.replace(",", "."))

        # Validate non-negative
        if min_savings < 0:
            await update.message.reply_text(
                "❌ *Valore non valido*\n\n"
                "Il risparmio minimo deve essere un numero non negativo.\n\n"
                "Esempio: `5` oppure `0` per qualsiasi risparmio\n\n"
                "Riprova oppure /cancel per annullare.",
                parse_mode="Markdown",
            )
            return WAITING_MIN_SAVINGS

        # Validate it's not greater than price paid
        price_paid = context.user_data["product_price"]
        if min_savings >= price_paid:
            await update.message.reply_text(
                "❌ *Valore troppo alto*\n\n"
                f"Il risparmio minimo (€{min_savings:.2f}) deve essere inferiore "
                f"al prezzo pagato (€{price_paid:.2f}).\n\n"
                "Riprova oppure /cancel per annullare.",
                parse_mode="Markdown",
            )
            return WAITING_MIN_SAVINGS

    except ValueError:
        await update.message.reply_text(
            "❌ *Valore non valido*\n\n"
            f"Non riesco a interpretare `{savings_str}` come un numero.\n\n"
            "Esempio: `5` oppure `0` per qualsiasi risparmio\n\n"
            "Riprova oppure /cancel per annullare.",
            parse_mode="Markdown",
        )
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
                "❌ *Limite prodotti raggiunto!*\n\n"
                f"Puoi monitorare al massimo *{user_limit} prodotti* contemporaneamente.\n\n"
                "Usa /delete per rimuovere un prodotto e fare spazio.",
                parse_mode="Markdown",
            )
            logger.info(f"User {user_id} reached product limit ({user_limit} products)")
            # Clear user_data and end conversation
            context.user_data.clear()
            return ConversationHandler.END

        # Add product to database
        await database.add_product(
            user_id=user_id,
            product_name=product_name,
            asin=asin,
            marketplace=marketplace,
            price_paid=price_paid,
            return_deadline=return_deadline,
            min_savings_threshold=min_savings,
        )

        # Build success message
        days_remaining = (return_deadline - date.today()).days
        message = (
            "✅ *Prodotto aggiunto con successo!*\n\n"
            f"📦 *{product_name}*\n"
            f"🔖 ASIN: `{asin}`\n"
            f"💰 Prezzo pagato: €{price_paid:.2f}\n"
            f"📅 Scadenza reso: {return_deadline.strftime('%d/%m/%Y')} (tra {days_remaining} giorni)\n"
        )

        if min_savings > 0:
            message += f"🎯 Risparmio minimo: €{min_savings:.2f}\n"
        else:
            message += "🎯 Notifica per qualsiasi risparmio\n"

        message += (
            "\n_Monitorerò il prezzo ogni giorno e ti avviserò se scende!_\n\n"
            "Usa /list per vedere tutti i tuoi prodotti."
        )

        await update.message.reply_text(message, parse_mode="Markdown")

        logger.info(
            f"Product added for user {user_id}: name={product_name}, ASIN={asin}, "
            f"price={price_paid}, deadline={return_deadline}, min_savings={min_savings}"
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
    - Date format gg-mm-aaaa: "09-05-2025" -> specific date
    - Date format yyyy-mm-dd (ISO): "2025-05-09" -> specific date (for /update compatibility)

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
            "Formato non valido. Usa giorni (es. `30`) o data gg-mm-aaaa (es. `09-05-2025`)"
        ) from None


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
