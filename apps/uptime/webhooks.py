from datetime import datetime

from apps.alerts.constants import RecipientType
from apps.alerts.models import AlertRecipient
from apps.alerts.webhooks import (
    DiscordEmbed,
    GoogleChatCard,
    MSTeamsSection,
    WebhookAttachment,
    send_discord_webhook,
    send_googlechat_webhook,
    send_telegram_webhook,
    send_webhook,
)

from .models import MonitorCheck


def send_uptime_as_webhook(
    recipient: AlertRecipient,
    monitor_check_id: int,
    went_down: bool,
    last_change: datetime,
):
    """
    Notification about uptime event via webhook.
    """
    monitor_check = MonitorCheck.objects.get(pk=monitor_check_id)
    monitor = monitor_check.monitor

    message = (
        "The monitored site has gone down."
        if went_down
        else "The monitored site is back up."
    )
    subject = "GlitchTip Uptime Alert"
    title = monitor.name

    if recipient.recipient_type == RecipientType.GENERAL_WEBHOOK:
        attachment = WebhookAttachment(title, monitor.get_detail_url(), message)
        section = MSTeamsSection(str(monitor.name), message)
        return send_webhook(recipient.url, subject, [attachment], [section])
    elif recipient.recipient_type == RecipientType.GOOGLE_CHAT:
        card = GoogleChatCard().construct_uptime_card(
            title=subject,
            subtitle=title,
            text=message,
            url=monitor.get_detail_url(),
        )
        return send_googlechat_webhook(recipient.url, [card])
    elif recipient.recipient_type == RecipientType.DISCORD:
        embed = DiscordEmbed(
            title=title,
            description=message,
            color=None,
            fields=[],
            url=monitor.get_detail_url(),
        )
        return send_discord_webhook(recipient.url, subject, [embed])
    elif recipient.recipient_type == RecipientType.TELEGRAM:
        # Parse chat_id from URL parameters
        from urllib.parse import parse_qs, urlparse

        parsed_url = urlparse(recipient.url)
        query_params = parse_qs(parsed_url.query)
        chat_id = query_params.get("chat_id", [""])[0]

        if not chat_id:
            # Try to extract chat_id from URL path if not in query params
            path_parts = parsed_url.path.split("/")
            if (
                len(path_parts) > 1
                and path_parts[-1]
                and path_parts[-1] != "sendMessage"
            ):
                chat_id = path_parts[-1]

        if not chat_id:
            raise ValueError("chat_id not found in URL")

        # Build the Telegram message with HTML formatting
        status_emoji = "🔴" if went_down else "🟢"
        message_parts = [
            f"{status_emoji} <b>{subject}</b>",
            "",
            f"<b>{title}</b>",
            f"<i>{message}</i>",
            "",
            f'🔗 <a href="{monitor.get_detail_url()}">View Monitor</a>',
        ]

        text = "\n".join(message_parts)

        # Remove chat_id from URL to get the base API URL
        base_url = recipient.url.split("?")[0]  # Remove query parameters
        if base_url.endswith(f"/{chat_id}"):
            base_url = base_url[: -len(f"/{chat_id}")]

        return send_telegram_webhook(base_url, text, chat_id)
