"""
Input validation functions for product data.

This module contains reusable validation logic extracted from add.py and update.py
to avoid duplication and improve testability.
"""

import re
from datetime import UTC, date, datetime, timedelta


def validate_product_name(name: str) -> tuple[bool, str | None, str | None]:
    """
    Validate product name length (3-100 characters).

    Args:
        name: Product name to validate (will be stripped)

    Returns:
        Tuple of (is_valid, cleaned_name, error_message)
        - is_valid: True if validation passed
        - cleaned_name: Stripped name if valid, None otherwise
        - error_message: User-friendly error message if invalid, None otherwise
    """
    cleaned_name = name.strip()

    if len(cleaned_name) < 3:
        return (
            False,
            None,
            (
                "❌ <b>Nome troppo corto</b>\n\n"
                "Il nome del prodotto deve contenere almeno 3 caratteri.\n\n"
                "Riprova oppure /cancel per annullare."
            ),
        )

    if len(cleaned_name) > 100:
        return (
            False,
            None,
            (
                "❌ <b>Nome troppo lungo</b>\n\n"
                "Il nome del prodotto può contenere al massimo 100 caratteri.\n\n"
                "Riprova oppure /cancel per annullare."
            ),
        )

    return True, cleaned_name, None


def validate_price(price_str: str, max_digits: int = 16) -> tuple[bool, float | None, str | None]:
    """
    Validate and parse price input.

    Args:
        price_str: Price string to parse (accepts ',' or '.' as decimal separator)
        max_digits: Maximum total number of digits allowed (default: 16)

    Returns:
        Tuple of (is_valid, parsed_price, error_message)
        - is_valid: True if validation passed
        - parsed_price: Float value if valid, None otherwise
        - error_message: User-friendly error message if invalid, None otherwise
    """
    price_str = price_str.strip()

    try:
        # Allow both comma and dot as decimal separator
        price = float(price_str.replace(",", "."))

        # Validate price is positive
        if price <= 0:
            return (
                False,
                None,
                (
                    "❌ <b>Prezzo non valido</b>\n\n"
                    "Il prezzo deve essere un numero positivo.\n\n"
                    "Esempio: <code>59.90</code> oppure <code>59,90</code>\n\n"
                    "Riprova oppure /cancel per annullare."
                ),
            )

        # Validate max digits (including decimals)
        digits_only = re.sub(r"[,.]", "", price_str)
        if len(digits_only) > max_digits:
            return (
                False,
                None,
                (
                    f"❌ <b>Prezzo troppo lungo</b>\n\n"
                    f"Il prezzo può contenere al massimo {max_digits} cifre in totale.\n\n"
                    "Riprova oppure /cancel per annullare."
                ),
            )

        return True, price, None

    except ValueError:
        return (
            False,
            None,
            (
                "❌ <b>Prezzo non valido</b>\n\n"
                f"Non riesco a interpretare <code>{price_str}</code> come un numero.\n\n"
                "Esempio: <code>59.90</code> oppure <code>59,90</code>\n\n"
                "Riprova oppure /cancel per annullare."
            ),
        )


def validate_threshold(
    threshold_str: str, max_value: float
) -> tuple[bool, float | None, str | None]:
    """
    Validate and parse minimum savings threshold.

    Args:
        threshold_str: Threshold string to parse (accepts ',' or '.' as decimal separator)
        max_value: Maximum allowed value (must be < price_paid)

    Returns:
        Tuple of (is_valid, parsed_threshold, error_message)
        - is_valid: True if validation passed
        - parsed_threshold: Float value if valid, None otherwise
        - error_message: User-friendly error message if invalid, None otherwise
    """
    threshold_str = threshold_str.strip()

    try:
        # Allow both comma and dot as decimal separator
        threshold = float(threshold_str.replace(",", "."))

        # Validate non-negative
        if threshold < 0:
            return (
                False,
                None,
                (
                    "❌ <b>Valore non valido</b>\n\n"
                    "Il risparmio minimo deve essere un numero non negativo.\n\n"
                    "Esempio: <code>5</code> oppure <code>0</code> per qualsiasi risparmio\n\n"
                    "Riprova oppure /cancel per annullare."
                ),
            )

        # Validate it's not greater than or equal to price paid
        if threshold >= max_value:
            return (
                False,
                None,
                (
                    "❌ <b>Valore troppo alto</b>\n\n"
                    f"Il risparmio minimo (€{threshold:.2f}) deve essere inferiore "
                    f"al prezzo pagato (€{max_value:.2f}).\n\n"
                    "Riprova oppure /cancel per annullare."
                ),
            )

        return True, threshold, None

    except ValueError:
        return (
            False,
            None,
            (
                "❌ <b>Valore non valido</b>\n\n"
                f"Non riesco a interpretare <code>{threshold_str}</code> come un numero.\n\n"
                "Esempio: <code>5</code> oppure <code>0</code> per qualsiasi risparmio\n\n"
                "Riprova oppure /cancel per annullare."
            ),
        )


def parse_deadline(deadline_input: str) -> date:
    """
    Parse deadline from user input.

    Accepts two formats:
    1. Number of days (1-365): "30" -> 30 days from today
    2. Date in format gg-mm-aaaa or gg/mm/aaaa: "09-05-2025" -> specific date

    Args:
        deadline_input: User input string

    Returns:
        Deadline as date object

    Raises:
        ValueError: If input format is invalid or out of range
    """
    deadline_input = deadline_input.strip()

    # Try parsing as number of days
    try:
        days = int(deadline_input)
        if days < 1 or days > 365:
            raise ValueError(
                "Il numero di giorni deve essere tra 1 e 365. "
                "Il bot ha bisogno di almeno 1 giorno per monitorare il prezzo!"
            )
        return datetime.now(UTC).date() + timedelta(days=days)
    except ValueError as e:
        # If it's our specific error about days range, re-raise it
        if "giorni deve essere" in str(e):
            raise
        # Otherwise, it's not a number, fall through to try date format

    # Try parsing as date (gg-mm-aaaa or gg/mm/aaaa)
    # Split by '-' or '/'
    parts = re.split(r"[-/]", deadline_input)

    if len(parts) != 3:
        raise ValueError(
            "Formato non valido. Usa giorni (es. 30) o data gg-mm-aaaa (es. 09-05-2025)"
        )

    try:
        # Handle both gg-mm-aaaa and aaaa-mm-gg formats
        # Check if first part is 4 digits (aaaa-mm-gg)
        if len(parts[0]) == 4:
            year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
        # Check if last part is 4 digits (gg-mm-aaaa or gg/mm/aaaa)
        elif len(parts[2]) == 4:
            day, month, year = int(parts[0]), int(parts[1]), int(parts[2])
        else:
            raise ValueError("Anno deve essere nel formato a 4 cifre (aaaa)")

        deadline = date(year, month, day)

        # Validate it's in the future (must be at least tomorrow, using UTC)
        today = datetime.now(UTC).date()
        if deadline <= today:
            if deadline == today:
                raise ValueError(
                    "La scadenza è oggi. Il bot ha bisogno di almeno 1 giorno "
                    "per monitorare il prezzo. Inserisci una data da domani in poi!"
                )
            else:
                raise ValueError(
                    f"La data specificata ({deadline.strftime('%d/%m/%Y')}) è nel passato. "
                    "Inserisci una data futura!"
                )

        return deadline

    except (ValueError, TypeError) as e:
        # Re-raise specific error messages
        if isinstance(e, ValueError):
            error_msg = str(e)
            if any(
                phrase in error_msg
                for phrase in [
                    "La data specificata",
                    "La scadenza è oggi",
                    "Anno deve essere",
                ]
            ):
                raise  # Re-raise our custom messages
        # Generic error for invalid dates
        raise ValueError(
            "Data non valida. Usa formato gg-mm-aaaa (es. 09-05-2025) o giorni (es. 30)"
        ) from None
