"""Keyboard building utilities for Telegram bot handlers."""

import html
from urllib.parse import quote

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def cancel_button(callback_data: str = "cancel") -> InlineKeyboardButton:
    """
    Create a cancel button.

    Args:
        callback_data: Callback data for the button

    Returns:
        Cancel button with standard styling
    """
    return InlineKeyboardButton("❌ Annulla", callback_data=callback_data)


def confirm_cancel_row(
    confirm_text: str,
    confirm_callback: str,
    cancel_callback: str,
    cancel_text: str = "❌ No, annulla",
) -> list[InlineKeyboardButton]:
    """
    Create a confirm/cancel button row.

    Args:
        confirm_text: Text for confirm button (e.g., "✅ Sì, elimina")
        confirm_callback: Callback data for confirm button
        cancel_callback: Callback data for cancel button
        cancel_text: Text for cancel button (default: "❌ No, annulla")

    Returns:
        List with confirm and cancel buttons for use as a keyboard row
    """
    return [
        InlineKeyboardButton(confirm_text, callback_data=confirm_callback),
        InlineKeyboardButton(cancel_text, callback_data=cancel_callback),
    ]


def confirm_cancel_keyboard(
    confirm_text: str,
    confirm_callback: str,
    cancel_callback: str,
    cancel_text: str = "❌ No, annulla",
) -> InlineKeyboardMarkup:
    """
    Create a keyboard with confirm/cancel buttons.

    Args:
        confirm_text: Text for confirm button
        confirm_callback: Callback data for confirm button
        cancel_callback: Callback data for cancel button
        cancel_text: Text for cancel button

    Returns:
        InlineKeyboardMarkup with confirm/cancel row
    """
    row = confirm_cancel_row(confirm_text, confirm_callback, cancel_callback, cancel_text)
    return InlineKeyboardMarkup([row])


def product_list_keyboard(
    products: list[dict],
    callback_prefix: str,
    cancel_callback: str,
) -> InlineKeyboardMarkup:
    """
    Create a keyboard with product selection buttons.

    Args:
        products: List of product dicts with keys: id, product_name, price_paid
        callback_prefix: Prefix for callback data (e.g., "delete_select" -> "delete_select_123")
        cancel_callback: Callback data for cancel button

    Returns:
        InlineKeyboardMarkup with one button per product plus cancel button
    """
    keyboard = []

    for idx, product in enumerate(products, start=1):
        product_id = product["id"]
        product_name = product.get("product_name") or f"Prodotto #{idx}"
        price_paid = product["price_paid"]

        # Button text shows index, name and price
        button_text = f"{idx}. {html.escape(product_name)} - €{price_paid:.2f}"
        callback_data = f"{callback_prefix}_{product_id}"

        keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])

    # Add cancel button
    keyboard.append([cancel_button(cancel_callback)])

    return InlineKeyboardMarkup(keyboard)


def share_button(
    text: str,
    share_message: str,
    share_url: str = "https://t.me/repackit_bot",
) -> InlineKeyboardMarkup:
    """
    Create a share button with pre-filled message.

    Args:
        text: Button text (e.g., "📢 Dillo a un amico")
        share_message: Pre-filled share message
        share_url: URL to share (default: bot link)

    Returns:
        InlineKeyboardMarkup with single share button
    """
    url = f"https://t.me/share/url?url={share_url}&text={quote(share_message)}"
    return InlineKeyboardMarkup([[InlineKeyboardButton(text, url=url)]])


def single_url_button(text: str, url: str) -> InlineKeyboardMarkup:
    """
    Create a keyboard with a single URL button.

    Args:
        text: Button text
        url: URL to open

    Returns:
        InlineKeyboardMarkup with single URL button
    """
    return InlineKeyboardMarkup([[InlineKeyboardButton(text, url=url)]])
