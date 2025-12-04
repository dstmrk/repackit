"""Handler for /start command."""

import logging

from telegram import Update
from telegram.ext import ContextTypes

import database
from config import get_config

logger = logging.getLogger(__name__)


async def _parse_referral_code(user_id: int, referral_code: str) -> tuple[int | None, str | None]:
    """
    Parse and validate referral code from /start parameter.

    Args:
        user_id: Current user's ID (to prevent self-referral)
        referral_code: Referral code from context.args[0]

    Returns:
        Tuple of (referrer_id, error_message)
        - referrer_id is None if invalid/self-referral
        - error_message is None if valid or silently ignored
    """
    # Validate referral code (must be positive integer)
    if not referral_code.isdigit():
        logger.warning(f"User {user_id} used malformed referral code: {referral_code}")
        return None, None

    referrer_id = int(referral_code)

    # Prevent self-referral (silently ignore)
    if referrer_id == user_id:
        logger.warning(f"User {user_id} attempted self-referral")
        return None, None

    # Invalid referrer ID
    if referrer_id <= 0:
        return None, None

    # Check if referrer exists
    referrer = await database.get_user(referrer_id)
    if referrer:
        logger.info(f"User {user_id} referred by {referrer_id}")
        return referrer_id, None

    # Referrer doesn't exist
    error_message = (
        "ℹ️ Il codice di invito che hai usato non è valido "
        "(l'invitante non risulta esistente).\n\n"
    )
    logger.warning(f"User {user_id} used invalid referral code {referrer_id}")
    return None, error_message


async def _register_new_user(user_id: int, language_code: str, referred_by: int | None) -> None:
    """
    Register new user in database with appropriate product limit.

    Args:
        user_id: User's Telegram ID
        language_code: User's language code
        referred_by: Referrer's user_id (None if no referral)
    """
    await database.add_user(user_id=user_id, language_code=language_code, referred_by=referred_by)

    # Set initial product limit
    if referred_by:
        # Invited user gets bonus: 3 base + 3 invited bonus = 6 slots
        initial_slots = database.INITIAL_MAX_PRODUCTS + database.INVITED_USER_BONUS
        await database.set_user_max_products(user_id, initial_slots)
        logger.info(
            f"New user {user_id} registered with {initial_slots} product slots "
            f"(referred by {referred_by})"
        )
    else:
        # Regular user: 3 slots
        await database.set_user_max_products(user_id, database.INITIAL_MAX_PRODUCTS)
        logger.info(
            f"New user {user_id} registered with {database.INITIAL_MAX_PRODUCTS} product slots"
        )


def _build_welcome_message(
    is_new_user: bool, has_referral_bonus: bool, referral_error: str | None
) -> str:
    """
    Build welcome message with appropriate sections.

    Args:
        is_new_user: True if this is a new user registration
        has_referral_bonus: True if user was invited and got bonus
        referral_error: Error message for invalid referral (None if valid)

    Returns:
        Formatted welcome message (HTML)
    """
    message = ""

    # Add referral error if applicable (only for new users)
    if referral_error and is_new_user:
        message += referral_error

    message += (
        "👋 <b>Benvenuto su RepackIt!</b>\n\n"
        "Ti aiuto a risparmiare monitorando i prezzi Amazon durante il periodo di reso.\n\n"
    )

    # Add referral bonus message for invited new users
    if is_new_user and has_referral_bonus:
        message += (
            "🎁 <b>Hai ricevuto 3 slot bonus</b> per essere stato invitato!\n"
            "Hai 6 slot disponibili per monitorare i tuoi prodotti.\n\n"
        )

    message += (
        "<b>Come funziona:</b>\n"
        "1️⃣ Aggiungi un prodotto che hai già acquistato\n"
        "2️⃣ Controllo il prezzo ogni giorno\n"
        "3️⃣ Ti avviso se scende, così puoi fare un nuovo ordine e restituire il precedente!\n\n"
        "<b>Comandi disponibili:</b>\n"
        "/add - Aggiungi un prodotto da monitorare\n"
        "/list - Visualizza i tuoi prodotti\n"
        "/delete - Rimuovi un prodotto\n"
        "/update - Modifica un prodotto\n"
        "/share - Invita amici e guadagna più slot\n"
        "/feedback - Invia un feedback\n\n"
        "Usa /help per maggiori informazioni!"
    )

    # Add channel reference if configured
    cfg = get_config()
    if cfg.telegram_channel:
        message += f"\n\n📢 Seguici su {cfg.telegram_channel} per aggiornamenti e novità!"

    return message


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle /start command.

    Registers new users and shows welcome message with bot instructions.
    Supports referral links: /start <referrer_user_id>

    Args:
        update: Telegram update object
        context: Telegram context object
    """
    user = update.effective_user
    user_id = user.id
    language_code = user.language_code

    logger.info(f"User {user_id} started the bot")

    # Parse referral code (if present)
    referred_by = None
    referral_error = None

    if context.args:
        referred_by, referral_error = await _parse_referral_code(user_id, context.args[0])

    # Register user in database if not exists
    existing_user = None
    try:
        existing_user = await database.get_user(user_id)
        if not existing_user:
            await _register_new_user(user_id, language_code, referred_by)
    except Exception as e:
        logger.error(f"Error registering user {user_id}: {e}", exc_info=True)

    # Build and send welcome message
    welcome_message = _build_welcome_message(
        is_new_user=not existing_user,
        has_referral_bonus=bool(referred_by),
        referral_error=referral_error,
    )
    await update.message.reply_text(welcome_message, parse_mode="HTML")
