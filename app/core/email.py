"""
Brevo transactional email service.
All functions save a Notification record in DB after sending.
"""
from __future__ import annotations

import logging
from datetime import date
from uuid import uuid4

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

BREVO_API_URL = "https://api.brevo.com/v3/smtp/email"


# ── Transport ─────────────────────────────────────────────────────────────────

def _send(to_email: str, to_name: str, subject: str, html: str) -> bool:
    """POST to Brevo API. Returns True on success, False on failure."""
    if not settings.BREVO_API_KEY:
        logger.warning("BREVO_API_KEY non configuré — email non envoyé à %s", to_email)
        return False

    payload = {
        "sender":  {"name": settings.EMAIL_FROM_NAME, "email": settings.EMAIL_FROM},
        "to":      [{"email": to_email, "name": to_name}],
        "subject": subject,
        "htmlContent": html,
    }
    headers = {
        "api-key":      settings.BREVO_API_KEY,
        "Content-Type": "application/json",
    }
    try:
        resp = httpx.post(BREVO_API_URL, json=payload, headers=headers, timeout=10)
        resp.raise_for_status()
        return True
    except httpx.HTTPStatusError as exc:
        logger.error("Brevo HTTP %s — %s", exc.response.status_code, exc.response.text)
        return False
    except httpx.RequestError as exc:
        logger.error("Brevo réseau — %s", exc)
        return False


# ── Templates ─────────────────────────────────────────────────────────────────

def _base_html(title: str, body: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <style>
    body {{ font-family: Georgia, serif; background:#F7F4EF; margin:0; padding:0; }}
    .wrap {{ max-width:600px; margin:40px auto; background:#fff; border-radius:8px; overflow:hidden; }}
    .header {{ background:#2D5016; padding:32px 40px; }}
    .header h1 {{ color:#C8A96E; margin:0; font-size:22px; letter-spacing:1px; }}
    .body {{ padding:32px 40px; color:#333; line-height:1.7; }}
    .body h2 {{ color:#2D5016; margin-top:0; }}
    .cta {{ display:inline-block; margin-top:24px; padding:12px 28px;
            background:#C8A96E; color:#fff; text-decoration:none;
            border-radius:4px; font-weight:bold; }}
    .footer {{ background:#F7F4EF; padding:16px 40px; font-size:12px; color:#888; }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="header"><h1>{settings.EMAIL_FROM_NAME}</h1></div>
    <div class="body">
      <h2>{title}</h2>
      {body}
    </div>
    <div class="footer">
      Vous recevez cet email car vous êtes membre de {settings.EMAIL_FROM_NAME}.
    </div>
  </div>
</body>
</html>"""


# ── Emails métier ─────────────────────────────────────────────────────────────

def send_welcome(to_email: str, first_name: str) -> bool:
    body = f"""
    <p>Bonjour <strong>{first_name}</strong>,</p>
    <p>Nous avons le plaisir de vous accueillir dans notre association.
       Votre compte membre est désormais actif.</p>
    <p>Si vous avez des questions, n'hésitez pas à contacter le secrétariat.</p>
    <p>Bienvenue parmi nous !</p>
    """
    return _send(
        to_email=to_email,
        to_name=first_name,
        subject=f"Bienvenue dans {settings.EMAIL_FROM_NAME} !",
        html=_base_html("Bienvenue !", body),
    )


def send_cotisation_reminder(
    to_email: str,
    first_name: str,
    month: int,
    year: int,
    amount: float,
) -> bool:
    month_names = [
        "", "janvier", "février", "mars", "avril", "mai", "juin",
        "juillet", "août", "septembre", "octobre", "novembre", "décembre",
    ]
    period = f"{month_names[month]} {year}"
    body = f"""
    <p>Bonjour <strong>{first_name}</strong>,</p>
    <p>Nous n'avons pas encore reçu votre cotisation pour <strong>{period}</strong>
       (montant : <strong>{amount:.2f} €</strong>).</p>
    <p>Merci de régulariser votre situation auprès du trésorier dès que possible.</p>
    <p>Si vous pensez qu'il s'agit d'une erreur, contactez-nous.</p>
    """
    return _send(
        to_email=to_email,
        to_name=first_name,
        subject=f"Rappel cotisation — {period}",
        html=_base_html(f"Rappel : cotisation {period}", body),
    )


def send_invite(to_email: str, invited_by_name: str, invite_link: str) -> bool:
    body = f"""
    <p>Bonjour,</p>
    <p><strong>{invited_by_name}</strong> vous invite à rejoindre notre association.</p>
    <p>Cliquez sur le bouton ci-dessous pour créer votre compte membre :</p>
    <a href="{invite_link}" class="cta">Créer mon compte</a>
    <p style="margin-top:20px;font-size:12px;color:#888;">
      Ce lien est valable 7 jours. Si vous n'êtes pas à l'origine de cette demande, ignorez cet email.
    </p>
    """
    return _send(
        to_email=to_email,
        to_name=to_email,
        subject=f"Invitation à rejoindre {settings.EMAIL_FROM_NAME}",
        html=_base_html("Vous êtes invité(e) !", body),
    )


def send_event_invitation(
    to_email: str,
    first_name: str,
    event_title: str,
    event_date: date,
    event_location: str | None,
) -> bool:
    location_line = f"<p>📍 Lieu : <strong>{event_location}</strong></p>" if event_location else ""
    body = f"""
    <p>Bonjour <strong>{first_name}</strong>,</p>
    <p>Nous avons le plaisir de vous inviter à l'événement suivant :</p>
    <p style="font-size:18px;color:#2D5016;"><strong>{event_title}</strong></p>
    <p>📅 Date : <strong>{event_date.strftime("%d %B %Y")}</strong></p>
    {location_line}
    <p>Pour vous inscrire, contactez le secrétariat ou rendez-vous sur votre espace membre.</p>
    """
    return _send(
        to_email=to_email,
        to_name=first_name,
        subject=f"Invitation — {event_title}",
        html=_base_html(f"Invitation : {event_title}", body),
    )
