"""Handler for /add command."""

import logging
from datetime import date, timedelta

from telegram import Update
from telegram.ext import ContextTypes

import database
from data_reader import extract_asin

logger = logging.getLogger(__name__)


async def _validate_inputs(
    url: str, price_str: str, deadline_str: str, threshold_str: str, message
) -> tuple[str, float, date, float] | None:
    """
    Validate and parse all input parameters for /add command.

    Returns:
        Tuple of (asin, price_paid, return_deadline, min_savings_threshold) or None if validation fails
    """
    # Extract ASIN from URL
    try:
        asin, _ = extract_asin(url)
    except ValueError as e:
        await message.reply_text(
            f"❌ URL Amazon non valido: {e}\n\nAssicurati di usare un link Amazon corretto."
        )
        return None

    # Parse price
    try:
        price_paid = float(price_str.replace(",", "."))
        if price_paid <= 0:
            raise ValueError("Price must be positive")
    except ValueError:
        await message.reply_text(
            f"❌ Prezzo non valido: `{price_str}`\n\nUsa un numero positivo (es. 59.90 o 59,90)",
            parse_mode="Markdown",
        )
        return None

    # Parse deadline
    try:
        return_deadline = parse_deadline(deadline_str)
    except ValueError as e:
        await message.reply_text(
            f"❌ Scadenza non valida: {e}\n\nUsa giorni (es. 30) o data ISO (es. 2024-12-25)",
        )
        return None

    # Check deadline is in the future
    if return_deadline < date.today():
        await message.reply_text(
            "❌ La scadenza deve essere nel futuro!\n\n"
            f"Data specificata: {return_deadline.strftime('%d/%m/%Y')}"
        )
        return None

    # Parse threshold (optional)
    min_savings_threshold = None
    if threshold_str:
        try:
            min_savings_threshold = float(threshold_str.replace(",", "."))
            if min_savings_threshold < 0:
                raise ValueError("Threshold must be non-negative")
            if min_savings_threshold >= price_paid:
                raise ValueError("Threshold must be less than price paid")
        except ValueError as e:
            await message.reply_text(
                f"❌ Soglia non valida: {e}\n\n"
                "La soglia deve essere un numero positivo minore del prezzo pagato.",
            )
            return None

    return asin, price_paid, return_deadline, min_savings_threshold


def parse_deadline(deadline_input: str, purchase_date: date = None) -> date:
    """
    Parse return deadline from user input.

    Supports two formats:
    - Number of days: "30" -> 30 days from purchase_date (or today)
    - ISO date: "2024-12-25" -> specific date

    Args:
        deadline_input: User input string
        purchase_date: Purchase date (defaults to today)

    Returns:
        Return deadline as date object

    Raises:
        ValueError: If input format is invalid
    """
    if purchase_date is None:
        purchase_date = date.today()

    # Try parsing as number of days
    try:
        days = int(deadline_input)
        if days <= 0:
            raise ValueError("Days must be positive")
        return purchase_date + timedelta(days=days)
    except ValueError as e:
        # If it's our custom error, re-raise it
        if "Days must be positive" in str(e):
            raise
        # Otherwise, continue to try date parsing

    # Try parsing as ISO date (YYYY-MM-DD)
    try:
        return date.fromisoformat(deadline_input)
    except ValueError:
        raise ValueError(
            "Invalid deadline format. Use days (e.g., '30') or date (e.g., '2024-12-25')"
        ) from None


async def add_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle /add command.

    Format: /add <url> <price> <deadline> [threshold]
    Examples:
    - /add https://amazon.it/dp/B08N5WRWNW 59.90 30
    - /add https://amazon.it/dp/B08N5WRWNW 59.90 2024-12-25 5

    Args:
        update: Telegram update object
        context: Telegram context object
    """
    user_id = update.effective_user.id

    # Check arguments
    if not context.args or len(context.args) < 3:
        await update.message.reply_text(
            "❌ *Utilizzo:* `/add <url> <prezzo> <giorni|data> [soglia]`\n\n"
            "*Esempi:*\n"
            "`/add https://amazon.it/dp/B08N5WRWNW 59.90 30`\n"
            "`/add https://amazon.it/dp/B08N5WRWNW 59.90 2024-12-25 5`\n\n"
            "*Parametri:*\n"
            "• `url`: Link Amazon del prodotto\n"
            "• `prezzo`: Prezzo pagato in euro\n"
            "• `giorni|data`: Giorni di reso (es. 30) o data scadenza (es. 2024-12-25)\n"
            "• `soglia`: (opzionale) Soglia minima di risparmio in euro",
            parse_mode="Markdown",
        )
        return

    url = context.args[0]
    price_str = context.args[1]
    deadline_str = context.args[2]
    threshold_str = context.args[3] if len(context.args) > 3 else None

    logger.info(f"User {user_id} adding product: {url}")

    try:
        # Validate and parse all inputs
        result = await _validate_inputs(url, price_str, deadline_str, threshold_str, update.message)
        if result is None:
            return
        asin, price_paid, return_deadline, min_savings_threshold = result

        # Register user if not exists
        await database.add_user(user_id=user_id, language_code=update.effective_user.language_code)

        # Add product to database
        await database.add_product(
            user_id=user_id,
            asin=asin,
            price_paid=price_paid,
            return_deadline=return_deadline,
            min_savings_threshold=min_savings_threshold,
        )

        # Build success message
        days_remaining = (return_deadline - date.today()).days
        message = (
            "✅ *Prodotto aggiunto con successo!*\n\n"
            f"📦 ASIN: `{asin}`\n"
            f"💰 Prezzo pagato: €{price_paid:.2f}\n"
            f"📅 Scadenza reso: {return_deadline.strftime('%d/%m/%Y')} (tra {days_remaining} giorni)\n"
        )

        if min_savings_threshold:
            message += f"🎯 Soglia risparmio: €{min_savings_threshold:.2f}\n"

        message += (
            "\n_Monitorerò il prezzo ogni giorno e ti avviserò se scende!_\n\n"
            "Usa /list per vedere tutti i tuoi prodotti."
        )

        await update.message.reply_text(message, parse_mode="Markdown")

        logger.info(
            f"Product added for user {user_id}: ASIN={asin}, price={price_paid}, deadline={return_deadline}"
        )

    except Exception as e:
        logger.error(f"Error in add_handler for user {user_id}: {e}", exc_info=True)
        await update.message.reply_text("❌ Errore nell'aggiungere il prodotto. Riprova più tardi.")
