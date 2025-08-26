from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING

import requests
from django.conf import settings
from django.db.models import F
from requests.exceptions import ReadTimeout

from .constants import RecipientType

if TYPE_CHECKING:
    from .models import Notification


@dataclass
class WebhookAttachmentField:
    title: str
    value: str
    short: bool


@dataclass
class WebhookAttachment:
    title: str
    title_link: str
    text: str
    image_url: str | None = None
    color: str | None = None
    fields: list[WebhookAttachmentField] | None = None
    mrkdown_in: list[str] | None = None


@dataclass
class MSTeamsSection:
    """
    Similar to WebhookAttachment but for MS Teams
    https://docs.microsoft.com/en-us/microsoftteams/platform/webhooks-and-connectors/how-to/connectors-using?tabs=cURL
    """

    activityTitle: str
    activitySubtitle: str


@dataclass
class WebhookPayload:
    alias: str
    text: str
    attachments: list[WebhookAttachment]
    sections: list[MSTeamsSection]


def send_webhook(
    url: str,
    message: str,
    attachments: list[WebhookAttachment] | None = None,
    sections: list[MSTeamsSection] | None = None,
):
    if not attachments:
        attachments = []
    if not sections:
        sections = []
    data = WebhookPayload(
        alias="GlitchTip", text=message, attachments=attachments, sections=sections
    )
    try:
        return requests.post(
            url,
            json=asdict(data),
            headers={"Content-type": "application/json"},
            timeout=10,
        )
    except ReadTimeout:
        # Ignore timeout
        return None


def send_issue_as_webhook(url, issues: list, issue_count: int = 1, **kwargs):
    """
    Notification about issues via webhook.
    url: Webhook URL
    issues: This should be only the issues to send as attachment
    issue_count - total issues, may be greater than len(issues)
    kwargs: Additional parameters
    """
    attachments: list[WebhookAttachment] = []
    sections: list[MSTeamsSection] = []
    for issue in issues:
        fields = [
            WebhookAttachmentField(
                title="Project",
                value=issue.project.name,
                short=True,
            )
        ]
        environment = (
            issue.issuetag_set.filter(tag_key__key="environment")
            .values(value=F("tag_value__value"))
            .first()
        )
        if environment:
            fields.append(
                WebhookAttachmentField(
                    title="Environment",
                    value=environment["value"],
                    short=True,
                )
            )
        server_name = (
            issue.issuetag_set.filter(tag_key__key="server_name")
            .values(value=F("tag_value__value"))
            .first()
        )
        if server_name:
            fields.append(
                WebhookAttachmentField(
                    title="Server Name",
                    value=server_name["value"],
                    short=True,
                )
            )
        release = (
            issue.issuetag_set.filter(tag_key__key="release")
            .values(value=F("tag_value__value"))
            .first()
        )
        if release:
            fields.append(
                WebhookAttachmentField(
                    title="Release",
                    value=release["value"],
                    short=False,
                )
            )

        tags_to_add = kwargs.get("tags_to_add", [])
        if tags_to_add:
            for tag in tags_to_add:
                tag_content = (
                    issue.issuetag_set.filter(tag_key__key=tag)
                    .values(value=F("tag_value__value"))
                    .first()
                )
                if tag_content:
                    fields.append(
                        WebhookAttachmentField(
                            title=tag.capitalize(),
                            value=tag_content["value"],
                            short=False,
                        )
                    )

        attachments.append(
            WebhookAttachment(
                mrkdown_in=["text"],
                title=str(issue),
                title_link=issue.get_detail_url(),
                text=issue.culprit,
                color=issue.get_hex_color(),
                fields=fields,
            )
        )
        sections.append(
            MSTeamsSection(
                activityTitle=str(issue),
                activitySubtitle=f"[View Issue {issue.short_id_display}]({issue.get_detail_url()})",
            )
        )
    message = "GlitchTip Alert"
    if issue_count > 1:
        message += f" ({issue_count} issues)"
    return send_webhook(url, message, attachments, sections)


@dataclass
class DiscordField:
    name: str
    value: str
    inline: bool = False


@dataclass
class DiscordEmbed:
    title: str
    description: str
    color: int
    url: str
    fields: list[DiscordField]


@dataclass
class DiscordWebhookPayload:
    content: str
    embeds: list[DiscordEmbed]


def send_issue_as_discord_webhook(url, issues: list, issue_count: int = 1, tags_to_add: list[str] | None = None):
    if tags_to_add is None:
        tags_to_add = []

    embeds: list[DiscordEmbed] = []

    for issue in issues:
        fields = [
            DiscordField(
                name="Project",
                value=issue.project.name,
                inline=True,
            )
        ]
        environment = (
            issue.issuetag_set.filter(tag_key__key="environment")
            .values(value=F("tag_value__value"))
            .first()
        )
        if environment:
            fields.append(
                DiscordField(
                    name="Environment",
                    value=environment["value"],
                    inline=True,
                )
            )
        release = (
            issue.issuetag_set.filter(tag_key__key="release")
            .values(value=F("tag_value__value"))
            .first()
        )
        if release:
            fields.append(
                DiscordField(
                    name="Release",
                    value=release["value"],
                    inline=False,
                )
            )
        server_name = (
            issue.issuetag_set.filter(tag_key__key="server_name")
            .values(value=F("tag_value__value"))
            .first()
        )
        if server_name:
            fields.append(
                DiscordField(
                    name="Server name",
                    value=server_name["value"],
                    inline=False,
                )
            )

        if tags_to_add:
            for tag in tags_to_add:
                tag_content = (
                    issue.issuetag_set.filter(tag_key__key=tag)
                    .values(value=F("tag_value__value"))
                    .first()
                )
                if tag_content:
                    fields.append(
                        DiscordField(
                            name=tag.capitalize(),
                            value=tag_content["value"],
                            inline=False,
                        )
                    )

        embeds.append(
            DiscordEmbed(
                title=str(issue),
                description=issue.culprit,
                color=int(issue.get_hex_color()[1:], 16)
                if issue.get_hex_color() is not None
                else None,
                url=issue.get_detail_url(),
                fields=fields,
            )
        )

    message = "GlitchTip Alert"
    if issue_count > 1:
        message += f" ({issue_count} issues)"

    return send_discord_webhook(url, message, embeds)


def send_discord_webhook(url: str, message: str, embeds: list[DiscordEmbed]):
    payload = DiscordWebhookPayload(content=message, embeds=embeds)
    return requests.post(url, json=asdict(payload), timeout=10)


@dataclass
class GoogleChatCard:
    header: dict | None = None
    sections: list[dict] | None = None

    def construct_uptime_card(self, title: str, subtitle: str, text: str, url: str):
        self.header = dict(
            title=title,
            subtitle=subtitle,
        )
        self.sections = [
            dict(
                widgets=[
                    dict(
                        decoratedText=dict(
                            text=text,
                            button=dict(
                                text="View", onClick=dict(openLink=dict(url=url))
                            ),
                        )
                    )
                ]
            )
        ]
        return self

    def construct_issue_card(self, title: str, issue, tags_to_add: list[str] | None = None):
        if tags_to_add is None:
            tags_to_add = []
            
        self.header = dict(title=title, subtitle=issue.project.name)
        section_header = "<font color='{}'>{}</font>".format(
            issue.get_hex_color(), str(issue)
        )
        widgets = []
        widgets.append(dict(decoratedText=dict(topLabel="Culprit", text=issue.culprit)))
        environment = (
            issue.issuetag_set.filter(tag_key__key="environment")
            .values(value=F("tag_value__value"))
            .first()
        )
        if environment:
            widgets.append(
                dict(
                    decoratedText=dict(
                        topLabel="Environment", text=environment["value"]
                    )
                )
            )
        server_name = (
            issue.issuetag_set.filter(tag_key__key="server_name")
            .values(value=F("tag_value__value"))
            .first()
        )
        if server_name:
            widgets.append(
                dict(
                    decoratedText=dict(
                        topLabel="Server Name", text=server_name["value"]
                    )
                )
            )
        release = (
            issue.issuetag_set.filter(tag_key__key="release")
            .values(value=F("tag_value__value"))
            .first()
        )
        if release:
            widgets.append(
                dict(decoratedText=dict(topLabel="Release", text=release["value"]))
            )

        if tags_to_add:
            for tag in tags_to_add:
                tag_content = (
                    issue.issuetag_set.filter(tag_key__key=tag)
                    .values(value=F("tag_value__value"))
                    .first()
                )
                if tag_content:
                    widgets.append(
                        dict(decoratedText=dict(topLabel=tag.capitalize(), text=tag_content["value"]))
                    )

        widgets.append(
            dict(
                buttonList=dict(
                    buttons=[
                        dict(
                            text="View Issue {}".format(issue.short_id_display),
                            onClick=dict(openLink=dict(url=issue.get_detail_url())),
                        )
                    ]
                )
            )
        )
        self.sections = [dict(header=section_header, widgets=widgets)]
        return self


@dataclass
class GoogleChatWebhookPayload:
    cardsV2: list[dict[str, GoogleChatCard]] = field(default_factory=list)

    def add_card(self, card):
        return self.cardsV2.append(dict(cardId="createCardMessage", card=card))


def send_googlechat_webhook(url: str, cards: list[GoogleChatCard]):
    """
    Send Google Chat compatible message as documented in
    https://developers.google.com/chat/messages-overview
    """
    payload = GoogleChatWebhookPayload()
    [payload.add_card(card) for card in cards]
    return requests.post(url, json=asdict(payload), timeout=10)


def send_issue_as_googlechat_webhook(url, issues: list, **kwargs):
    cards = []
    for issue in issues:
        card = GoogleChatCard().construct_issue_card(
            title="GlitchTip Alert", issue=issue, tags_to_add=kwargs.get("tags_to_add", [])
        )
        cards.append(card)
    return send_googlechat_webhook(url, cards)


@dataclass
class TelegramWebhookPayload:
    chat_id: str
    text: str
    parse_mode: str = "HTML"
    disable_web_page_preview: bool = True


def send_telegram_webhook(url: str, text: str, chat_id: str):
    """
    Send message via Telegram Bot API
    url: Bot API URL (https://api.telegram.org/bot{token}/sendMessage)
    text: Message text (HTML formatted)
    chat_id: Chat or group ID
    """
    payload = TelegramWebhookPayload(chat_id=chat_id, text=text)
    return requests.post(url, json=asdict(payload), timeout=10)


def send_issue_as_telegram_webhook(url, issues: list, issue_count: int = 1, tags_to_add: list[str] | None = None):
    """
    Format and send issues to Telegram webhook
    URL format: https://api.telegram.org/bot{token}/sendMessage?chat_id={chat_id}
    """
    if tags_to_add is None:
        tags_to_add = []

    # Parse chat_id from URL parameters
    from urllib.parse import parse_qs, urlparse
    parsed_url = urlparse(url)
    query_params = parse_qs(parsed_url.query)
    chat_id = query_params.get('chat_id', [''])[0]
    
    if not chat_id:
        # Try to extract chat_id from URL path if not in query params
        # Format: https://api.telegram.org/bot{token}/sendMessage/{chat_id}
        path_parts = parsed_url.path.split('/')
        if len(path_parts) > 1 and path_parts[-1] and path_parts[-1] != 'sendMessage':
            chat_id = path_parts[-1]
    
    if not chat_id:
        raise ValueError("chat_id not found in URL")

    # Build the message text
    message_parts = ["🚨 <b>GlitchTip Alert</b>"]
    if issue_count > 1:
        message_parts[0] += f" ({issue_count} issues)"
    
    for issue in issues:
        message_parts.append("")  # Empty line
        message_parts.append(f"<b>{issue}</b>")
        
        if issue.culprit:
            message_parts.append(f"<i>{issue.culprit}</i>")
        
        # Add project info
        message_parts.append(f"📁 Project: {issue.project.name}")
        
        # Add environment if available
        environment = (
            issue.issuetag_set.filter(tag_key__key="environment")
            .values(value=F("tag_value__value"))
            .first()
        )
        if environment:
            message_parts.append(f"🌍 Environment: {environment['value']}")
        
        # Add server name if available
        server_name = (
            issue.issuetag_set.filter(tag_key__key="server_name")
            .values(value=F("tag_value__value"))
            .first()
        )
        if server_name:
            message_parts.append(f"🖥️ Server: {server_name['value']}")
        
        # Add release if available
        release = (
            issue.issuetag_set.filter(tag_key__key="release")
            .values(value=F("tag_value__value"))
            .first()
        )
        if release:
            message_parts.append(f"🚀 Release: {release['value']}")
        
        # Add custom tags
        if tags_to_add:
            for tag in tags_to_add:
                tag_content = (
                    issue.issuetag_set.filter(tag_key__key=tag)
                    .values(value=F("tag_value__value"))
                    .first()
                )
                if tag_content:
                    message_parts.append(f"🏷️ {tag.capitalize()}: {tag_content['value']}")
        
        # Add link to issue
        issue_url = issue.get_detail_url()
        if issue_url:
            message_parts.append(f"🔗 <a href=\"{issue_url}\">View Issue {issue.short_id_display}</a>")
    
    text = "\n".join(message_parts)
    
    # Remove chat_id from URL to get the base API URL
    base_url = url.split('?')[0]  # Remove query parameters
    if base_url.endswith(f"/{chat_id}"):
        base_url = base_url[:-len(f"/{chat_id}")]
    
    return send_telegram_webhook(base_url, text, chat_id)


def send_webhook_notification(
    notification: "Notification", url: str, recipient_type: str, tags_to_add: list[str] | None = None
):
    issue_count = notification.issues.count()
    issues = notification.issues.all()[: settings.MAX_ISSUES_PER_ALERT]


    if recipient_type == RecipientType.DISCORD:
        send_issue_as_discord_webhook(url, issues, issue_count, tags_to_add=tags_to_add)
    elif recipient_type == RecipientType.GOOGLE_CHAT:
        send_issue_as_googlechat_webhook(url, issues, tags_to_add=tags_to_add)
    elif recipient_type == RecipientType.TELEGRAM:
        send_issue_as_telegram_webhook(url, issues, issue_count, tags_to_add=tags_to_add)
    else:
        send_issue_as_webhook(url, issues, issue_count, tags_to_add=tags_to_add)
