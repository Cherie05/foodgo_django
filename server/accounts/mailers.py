# accounts/mailers.py
import os, json, requests
from django.core.mail import send_mail

BREVO_API_KEY = os.getenv("BREVO_API_KEY", "")
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "FoodGo <no-reply@example.com>")
EMAIL_MODE = os.getenv("EMAIL_MODE", "smtp").lower()
BREVO_API_URL = "https://api.brevo.com/v3/smtp/email"

def _from_address():
    if "<" in DEFAULT_FROM_EMAIL and ">" in DEFAULT_FROM_EMAIL:
        return DEFAULT_FROM_EMAIL.split("<", 1)[1].split(">", 1)[0].strip()
    return DEFAULT_FROM_EMAIL

def _send_via_brevo_api(to_email: str, subject: str, text: str) -> None:
    if not BREVO_API_KEY:
        raise RuntimeError("BREVO_API_KEY missing; cannot send via API")
    headers = {
        "accept": "application/json",
        "api-key": BREVO_API_KEY,
        "content-type": "application/json",
    }
    payload = {
        "sender": {"email": _from_address(), "name": "FoodGo"},
        "to": [{"email": to_email}],
        "subject": subject,
        "textContent": text,
    }
    r = requests.post(BREVO_API_URL, headers=headers, data=json.dumps(payload), timeout=12)
    r.raise_for_status()

def send_otp_email(to_email: str, subject: str, text: str) -> None:
    # Try SMTP if requested; fallback to API on failure (PA free blocks most SMTP).
    if EMAIL_MODE == "smtp":
        try:
            send_mail(subject, text, None, [to_email], fail_silently=False)
            return
        except Exception:
            _send_via_brevo_api(to_email, subject, text)
            return
    elif EMAIL_MODE == "brevo_api":
        _send_via_brevo_api(to_email, subject, text)
    else:
        print(f"[DEV EMAIL] To: {to_email}\nSubj: {subject}\n{text}")
