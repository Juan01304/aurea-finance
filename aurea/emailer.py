from __future__ import annotations

import json
import os
import smtplib
import ssl
import urllib.error
import urllib.request
from email.message import EmailMessage


def _resend(to_email: str, subject: str, text: str) -> None:
    key = os.environ.get("RESEND_API_KEY", "").strip()
    if not key:
        raise RuntimeError("RESEND_API_KEY ausente")
    sender = os.environ.get("RESEND_FROM", "Aurea Finance <onboarding@resend.dev>").strip()
    payload = {"from": sender, "to": [to_email], "subject": subject, "text": text}
    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            if response.status >= 300:
                raise RuntimeError(f"Resend HTTP {response.status}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:300]
        raise RuntimeError(f"Resend HTTP {exc.code}: {detail}") from exc


def _smtp(to_email: str, subject: str, text: str) -> None:
    host = os.environ.get("SMTP_HOST", "").strip()
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ.get("SMTP_USER", "").strip()
    password = os.environ.get("SMTP_PASS", "")
    sender = os.environ.get("SMTP_FROM", user).strip()
    if not host or not sender:
        raise RuntimeError("SMTP não configurado")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = to_email
    msg.set_content(text)

    if port == 465:
        with smtplib.SMTP_SSL(host, port, context=ssl.create_default_context(), timeout=20) as smtp:
            if user:
                smtp.login(user, password)
            smtp.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=20) as smtp:
            smtp.ehlo()
            smtp.starttls(context=ssl.create_default_context())
            smtp.ehlo()
            if user:
                smtp.login(user, password)
            smtp.send_message(msg)


def send_otp(to_email: str, code: str, purpose: str) -> str:
    labels = {
        "verify": ("Confirme seu e-mail na Aurea", "confirmação de e-mail"),
        "login": ("Seu código de acesso da Aurea", "acesso em duas etapas"),
        "reset": ("Recupere sua senha da Aurea", "recuperação de senha"),
    }
    subject, label = labels.get(purpose, ("Seu código da Aurea", "verificação"))
    text = (
        f"Seu código de {label} é: {code}\n\n"
        "Ele expira em 10 minutos e só pode ser usado uma vez.\n"
        "Se você não solicitou este código, ignore esta mensagem."
    )

    if os.environ.get("RESEND_API_KEY", "").strip():
        _resend(to_email, subject, text)
        return "resend"
    if os.environ.get("SMTP_HOST", "").strip():
        _smtp(to_email, subject, text)
        return "smtp"

    print(f"[AUREA OTP] {purpose} {to_email}: {code}")
    return "console"
