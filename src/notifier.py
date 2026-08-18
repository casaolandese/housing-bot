"""Email alerts.

The brief: every alert must carry all the decision-relevant facts inline, so the
inbox alone is enough to judge a listing, plus one direct link to apply. The
card is therefore a dense label/value grid rather than a teaser - tables and
inline styles only, because Gmail strips <style> blocks and flexbox/grid.
"""
import html
import logging
import smtplib
import ssl
from email.message import EmailMessage
from typing import List, Optional

from src import config
from src.parsers.base import Listing

log = logging.getLogger(__name__)

ACCENT = "#e05d2f"
INK = "#16181d"
MUTED = "#6b7280"
LINE = "#e5e7eb"


def _fact_rows(l: Listing) -> List[tuple]:
    """Only include facts we actually have - no 'n/a' padding."""
    rent = None
    if l.price is not None:
        rent = "EUR %s/mo" % l.price
        if l.utilities_included:
            rent += " (utilities incl.)"
    rows = [
        ("Rent", rent),
        ("Deposit", "EUR %s" % l.deposit if l.deposit else None),
        ("Registration", "EUR %s" % l.registration_cost if l.registration_cost else None),
        ("Size", "%s m2" % l.surface_area if l.surface_area else None),
        ("Type", l.room_type or None),
        ("City", l.city or None),
        ("Address", ", ".join(filter(None, [l.street, l.postal_code])) or None),
        ("Available", l.available_from or None),
        ("Until", l.available_until or None),
        ("Furnished", l.furnished or None),
        ("Tenant gender", l.gender_pref or None),
        ("Tenant type", l.occupancy or None),
        ("Age range", "%s yrs" % l.age_range if l.age_range else None),
        ("Housemates", l.housemates or None),
        ("Landlord", l.landlord or None),
        ("Posted", l.published or None),
        ("Viewing", l.viewing_date or None),
    ]
    return [(k, v) for k, v in rows if v]


def _card_html(l: Listing) -> str:
    facts = _fact_rows(l)
    cells = ""
    for i, (k, v) in enumerate(facts):
        if i % 2 == 0:
            cells += "<tr>"
        cells += (
            '<td style="padding:5px 10px 5px 0;vertical-align:top;width:50%;">'
            '<div style="font:600 10px/1.4 Arial,sans-serif;letter-spacing:.06em;'
            'text-transform:uppercase;color:' + MUTED + ';">' + html.escape(k) + '</div>'
            '<div style="font:400 14px/1.4 Arial,sans-serif;color:' + INK + ';">'
            + html.escape(str(v)) + '</div></td>'
        )
        if i % 2 == 1 or i == len(facts) - 1:
            if i % 2 == 0:
                cells += '<td style="width:50%"></td>'
            cells += "</tr>"

    desc = ""
    if l.description:
        snippet = l.description[:340] + ("..." if len(l.description) > 340 else "")
        desc = ('<p style="margin:14px 0 0;font:400 13px/1.55 Arial,sans-serif;color:'
                + MUTED + ';border-top:1px solid ' + LINE + ';padding-top:12px;">'
                + html.escape(snippet) + '</p>')

    img = ""
    if l.image_url:
        img = ('<img src="' + html.escape(l.image_url) + '" width="560" '
               'style="width:100%;max-width:560px;height:auto;'
               'border-radius:8px 8px 0 0;display:block;" alt="">')

    price = "EUR %s" % l.price if l.price is not None else "EUR ?"
    return (
        '<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%"'
        ' style="max-width:600px;margin:0 auto 22px;border:1px solid ' + LINE + ';'
        'border-radius:10px;overflow:hidden;background:#fff;">'
        '<tr><td>' + img + '</td></tr>'
        '<tr><td style="padding:18px 20px 6px;">'
        '<div style="font:700 24px/1.2 Arial,sans-serif;color:' + INK + ';">' + price +
        '<span style="font:400 15px/1.2 Arial,sans-serif;color:' + MUTED + ';">/mo &middot; '
        + html.escape(l.room_type or "Room") + ' &middot; ' + html.escape(l.city or "") +
        '</span></div>'
        '<div style="font:400 15px/1.4 Arial,sans-serif;color:' + INK + ';margin-top:5px;">'
        + html.escape(l.title or "") + '</div></td></tr>'
        '<tr><td style="padding:10px 20px 0;">'
        '<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%">'
        + cells + '</table>' + desc + '</td></tr>'
        '<tr><td style="padding:18px 20px 22px;">'
        '<a href="' + html.escape(l.url) + '" style="display:block;background:' + ACCENT +
        ';color:#fff;text-decoration:none;font:700 15px/1 Arial,sans-serif;padding:14px 20px;'
        'border-radius:8px;text-align:center;">View &amp; apply on '
        + html.escape(l.source.title()) + ' &rarr;</a>'
        '<div style="font:400 11px/1.4 Arial,sans-serif;color:' + MUTED + ';margin-top:8px;'
        'text-align:center;word-break:break-all;">' + html.escape(l.url) + '</div>'
        '</td></tr></table>'
    )


def _card_text(l: Listing) -> str:
    head = ("EUR %s" % l.price if l.price is not None else "EUR ?")
    lines = ["%s/mo | %s | %s" % (head, l.room_type, l.city), l.title or ""]
    lines += ["  %s: %s" % (k, v) for k, v in _fact_rows(l)]
    if l.description:
        lines.append("  " + l.description[:300])
    lines.append("  APPLY: " + l.url)
    return "\n".join(lines)


def _wrap(inner: str, heading: str) -> str:
    return (
        '<div style="background:#f4f5f7;padding:22px 12px;margin:0;">'
        '<div style="max-width:600px;margin:0 auto 14px;font:700 13px/1.3 Arial,sans-serif;'
        'color:' + MUTED + ';letter-spacing:.04em;">' + html.escape(heading) + '</div>'
        + inner +
        '<div style="max-width:600px;margin:6px auto 0;font:400 11px/1.5 Arial,sans-serif;'
        'color:' + MUTED + ';text-align:center;">Housing bot &middot; Amsterdam &amp; Utrecht'
        ' &middot; rooms up to EUR ' + str(config.MAX_RENT) +
        ' &middot; each listing is sent once.</div></div>'
    )


def _send(subject: str, html_body: str, text_body: str) -> bool:
    if config.DRY_RUN:
        log.info("[DRY_RUN] would send: %s", subject)
        return True
    if not (config.SMTP_EMAIL and config.SMTP_APP_PASSWORD and config.ALERT_RECIPIENT_EMAIL):
        log.error("SMTP env vars missing; cannot send '%s'", subject)
        return False

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = config.SMTP_EMAIL
    msg["To"] = config.ALERT_RECIPIENT_EMAIL
    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")
    try:
        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL(config.SMTP_HOST, config.SMTP_PORT, context=ctx, timeout=30) as s:
            s.login(config.SMTP_EMAIL, config.SMTP_APP_PASSWORD)
            s.send_message(msg)
        log.info("sent: %s", subject)
        return True
    except Exception as exc:  # noqa: BLE001
        log.error("send failed (%s): %s", subject, exc)
        return False


def send_listing(l: Listing) -> bool:
    subject = "[Housing Alert] EUR %s - %s in %s" % (l.price, l.room_type, l.city)
    return _send(subject,
                 _wrap(_card_html(l), "New listing matching your search"),
                 _card_text(l))


def send_digest(listings: List[Listing], note: Optional[str] = None) -> bool:
    prices = [l.price for l in listings if l.price is not None]
    span = "EUR %s-%s" % (min(prices), max(prices)) if prices else ""
    cities = sorted({l.city for l in listings if l.city})
    subject = "[Housing Alert] %d new rooms %s in %s" % (
        len(listings), span, ", ".join(cities[:3]))
    heading = note or "%d new listings matching your search" % len(listings)
    html_body = _wrap("".join(_card_html(l) for l in listings), heading)
    text_body = (note + "\n\n" if note else "") + "\n\n".join(_card_text(l) for l in listings)
    return _send(subject, html_body, text_body)


def notify(listings: List[Listing], first_run: bool = False) -> int:
    """Few listings -> one email each (fastest to act on). Many -> one digest."""
    if not listings:
        return 0
    listings = sorted(listings, key=lambda l: (l.price is None, l.price or 0))
    cap = config.MAX_EMAILS_PER_RUN * 3
    if first_run:
        send_digest(listings[:cap],
                    note="First run: seeding the database. These are current "
                         "matches, not brand-new posts. From now on you will "
                         "only be alerted about genuinely new listings.")
        return 1
    if len(listings) <= config.INDIVIDUAL_EMAIL_THRESHOLD:
        return sum(1 for l in listings if send_listing(l))
    return 1 if send_digest(listings[:cap]) else 0
