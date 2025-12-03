"""Centralized message templates for bot responses.

This module follows the Message Builder Pattern to eliminate message duplication
across handlers. All user-facing messages should be defined here with clear,
reusable functions.

Message Format:
- All messages use HTML formatting (parse_mode="HTML")
- Bold: <b>text</b>
- Italic: <i>text</i>
- Code: <code>text</code>
- Links: <a href="url">text</a>
"""

import database

# ============================================================================
# Cancellation Messages
# ============================================================================


def cancel_operation() -> str:
    """
    Generic cancellation message for any operation.

    Used in: /add, /update, /delete
    """
    return "❌ <b>Operazione annullata</b>\n\nNessuna modifica è stata effettuata."


def cancel_feedback() -> str:
    """
    Cancellation message for /feedback command.

    Used in: /feedback
    """
    return "❌ <b>Feedback annullato</b>\n\nNessun messaggio è stato inviato."


# ============================================================================
# Slot Management Messages
# ============================================================================


def slot_hint() -> str:
    """
    Build hint message when user is running low on slots.

    Logic: Show hint if user has <3 slots available and limit < max cap (21).

    Returns:
        HTML-formatted hint message

    Used in: /add (after success), /list (in product list)

    Examples:
        >>> slot_hint()
        '💡 <b>Suggerimento:</b> Stai esaurendo gli slot! Usa /share per invitare...'
    """
    return (
        "💡 <b>Suggerimento:</b> Stai esaurendo gli slot! "
        "Usa /share per invitare amici e guadagnare più spazio."
    )


def should_show_slot_hint(current: int, limit: int) -> bool:
    """
    Check if slot hint should be shown to user.

    Logic:
    - User must have <3 slots available
    - User must not be at max capacity (21 slots)

    Args:
        current: Current number of monitored products
        limit: User's product slot limit

    Returns:
        True if hint should be shown, False otherwise

    Used in: /add, /list
    """
    slots_available = limit - current
    max_slots = database.DEFAULT_MAX_PRODUCTS
    return limit < max_slots and slots_available < 3


def referral_bonus_notification(new_limit: int) -> str:
    """
    Notification message when user receives referral bonus.

    Sent to inviter when invitee adds their first product.

    Args:
        new_limit: User's new product limit after bonus

    Returns:
        HTML-formatted notification message

    Used in: /add (when first product added by referred user)
    """
    return (
        "🎉 Un amico che hai invitato ha aggiunto il suo primo prodotto!\n"
        f"💎 Hai ricevuto +3 slot (ora ne hai {new_limit}/{database.DEFAULT_MAX_PRODUCTS})"
    )


# ============================================================================
# Product Management Messages
# ============================================================================


def product_added_success(
    product_name: str,
    asin: str,
    price: float,
    deadline_str: str,
    days_remaining: int,
    threshold: float,
) -> str:
    """
    Success message after adding a product.

    Args:
        product_name: User-defined product name (should be pre-escaped with html.escape())
        asin: Amazon Standard Identification Number
        price: Price paid in euros
        deadline_str: Return deadline formatted as dd/mm/yyyy
        days_remaining: Days until deadline
        threshold: Minimum savings threshold (0 = any savings)

    Returns:
        HTML-formatted success message

    Used in: /add
    """
    message = (
        "✅ <b>Prodotto aggiunto con successo!</b>\n\n"
        f"📦 <b>{product_name}</b>\n"
        f"🔖 ASIN: <code>{asin}</code>\n"
        f"💰 Prezzo pagato: €{price:.2f}\n"
        f"📅 Scadenza reso: {deadline_str} (tra {days_remaining} giorni)\n"
    )

    if threshold > 0:
        message += f"🎯 Risparmio minimo: €{threshold:.2f}\n"
    else:
        message += "🎯 Notifica per qualsiasi risparmio\n"

    message += (
        "\n<i>Monitorerò il prezzo ogni giorno e ti avviserò se scende!</i>\n\n"
        "Usa /list per vedere tutti i tuoi prodotti."
    )

    return message


def product_deleted_success(product_name: str) -> str:
    """
    Success message after deleting a product.

    Args:
        product_name: Name of deleted product (should be pre-escaped with html.escape())

    Returns:
        HTML-formatted success message

    Used in: /delete
    """
    return (
        "✅ <b>Prodotto eliminato con successo!</b>\n\n"
        f"📦 <b>{product_name}</b>\n\n"
        "Il prodotto non sarà più monitorato.\n"
        "Usa /list per vedere i tuoi prodotti rimanenti."
    )


def product_updated_success(product_name: str, field: str, new_value: str) -> str:
    """
    Success message after updating a product field.

    Args:
        product_name: Name of updated product
        field: Field that was updated (human-readable)
        new_value: New value (formatted)

    Returns:
        HTML-formatted success message

    Used in: /update
    """
    return (
        "✅ <b>Prodotto aggiornato con successo!</b>\n\n"
        f"📦 {product_name}\n"
        f"{field}: <b>{new_value}</b>"
    )


# ============================================================================
# Error Messages
# ============================================================================


def product_limit_reached(current: int, limit: int) -> str:
    """
    Error message when user has reached product limit.

    Args:
        current: Current number of products
        limit: User's product limit

    Returns:
        HTML-formatted error message

    Used in: /add
    """
    return (
        f"❌ <b>Limite raggiunto!</b>\n\n"
        f"Hai già {current}/{limit} prodotti monitorati.\n\n"
        "💡 <b>Suggerimenti:</b>\n"
        "• Usa /delete per rimuovere un prodotto\n"
        "• Usa /share per invitare amici e guadagnare più slot"
    )


def no_products_found() -> str:
    """
    Message when user has no products to list/delete/update.

    Returns:
        HTML-formatted message

    Used in: /list, /delete, /update
    """
    return (
        "📭 <b>Nessun prodotto monitorato</b>\n\n" "Usa /add per aggiungere il tuo primo prodotto!"
    )


def invalid_url() -> str:
    """
    Error message for invalid Amazon URL.

    Returns:
        HTML-formatted error message

    Used in: /add
    """
    return (
        "❌ <b>URL non valido</b>\n\n"
        "Invia un link Amazon.it valido.\n\n"
        "<b>Esempio:</b>\n"
        "<code>https://amazon.it/dp/B08N5WRWNW</code>\n\n"
        "Oppure scrivi /cancel per annullare."
    )


def invalid_price() -> str:
    """
    Error message for invalid price input.

    Returns:
        HTML-formatted error message

    Used in: /add, /update
    """
    return (
        "❌ <b>Prezzo non valido</b>\n\n"
        "Invia un prezzo valido in euro.\n\n"
        "<b>Esempi:</b>\n"
        "• <code>59.90</code>\n"
        "• <code>59,90</code>\n\n"
        "Oppure scrivi /cancel per annullare."
    )


def invalid_deadline() -> str:
    """
    Error message for invalid deadline input.

    Returns:
        HTML-formatted error message

    Used in: /add, /update
    """
    return (
        "❌ <b>Scadenza non valida</b>\n\n"
        "Invia una scadenza valida:\n\n"
        "<b>Opzione 1 - Numero di giorni (1-365):</b>\n"
        "• <code>30</code> → 30 giorni da oggi\n\n"
        "<b>Opzione 2 - Data (gg-mm-aaaa):</b>\n"
        "• <code>31-12-2025</code>\n\n"
        "Oppure scrivi /cancel per annullare."
    )


def invalid_threshold() -> str:
    """
    Error message for invalid savings threshold.

    Returns:
        HTML-formatted error message

    Used in: /add, /update
    """
    return (
        "❌ <b>Soglia non valida</b>\n\n"
        "Invia un valore valido:\n\n"
        "<b>Esempi:</b>\n"
        "• <code>0</code> → notifica per qualsiasi ribasso\n"
        "• <code>5</code> → notifica solo se risparmi almeno €5\n\n"
        "Oppure scrivi /cancel per annullare."
    )


def invalid_product_name() -> str:
    """
    Error message for invalid product name.

    Returns:
        HTML-formatted error message

    Used in: /add, /update
    """
    return (
        "❌ <b>Nome non valido</b>\n\n"
        "Il nome deve essere tra 3 e 100 caratteri.\n\n"
        "<b>Esempi:</b>\n"
        "• <code>iPhone 15 Pro</code>\n"
        "• <code>Cuffie Sony WH-1000XM5</code>\n\n"
        "Oppure scrivi /cancel per annullare."
    )


# ============================================================================
# Feedback Messages
# ============================================================================


def feedback_success() -> str:
    """
    Success message after submitting feedback.

    Returns:
        HTML-formatted success message

    Used in: /feedback
    """
    return (
        "✅ <b>Feedback inviato con successo!</b>\n\n"
        "Grazie per il tuo feedback! Lo esamineremo al più presto per migliorare il servizio.\n\n"
        "Il tuo contributo è molto importante per noi! 🙏"
    )


def feedback_rate_limited(hours_remaining: int = None, minutes_remaining: int = None) -> str:
    """
    Error message when user tries to send feedback too frequently.

    Args:
        hours_remaining: Hours until next feedback allowed (if >= 1 hour)
        minutes_remaining: Minutes until next feedback allowed (if < 1 hour)

    Returns:
        HTML-formatted error message

    Used in: /feedback
    """
    if hours_remaining and hours_remaining >= 1:
        time_str = f"{hours_remaining} {'ora' if hours_remaining == 1 else 'ore'}"
    elif minutes_remaining:
        time_str = f"{minutes_remaining} {'minuto' if minutes_remaining == 1 else 'minuti'}"
    else:
        time_str = "poco tempo"

    return (
        "⏳ <b>Feedback già inviato di recente</b>\n\n"
        "Puoi inviare un feedback ogni 24 ore.\n\n"
        f"Riprova tra {time_str}."
    )


def feedback_too_short() -> str:
    """
    Error message when feedback is too short (<10 characters).

    Returns:
        HTML-formatted error message

    Used in: /feedback
    """
    return (
        "❌ <b>Messaggio troppo breve</b>\n\n"
        "Il feedback deve contenere almeno 10 caratteri.\n\n"
        "Scrivi un messaggio più dettagliato oppure usa /cancel per annullare."
    )


def feedback_too_long() -> str:
    """
    Error message when feedback is too long (>1000 characters).

    Returns:
        HTML-formatted error message

    Used in: /feedback
    """
    return (
        "❌ <b>Messaggio troppo lungo</b>\n\n"
        "Il feedback non può superare i 1000 caratteri.\n\n"
        "Riduci il messaggio oppure usa /cancel per annullare."
    )
