"""Emergency card: the life-critical facts on one printable card with a QR code.

Fills the gap when hospitals are not connected: the patient carries the card (or a
photo of it); any clinician can read it, or scan the QR code with a phone camera,
with no login or internet. The QR code holds plain text, so no app is needed to read it.
"""
from __future__ import annotations

import io
from datetime import date

import qrcode
from PIL import Image, ImageDraw, ImageFont

RED, DARK, MUTED, LINE = (180, 35, 24), (28, 39, 51), (99, 113, 132), (226, 231, 238)


def card_text(patient: dict, summary: dict, max_items: int = 6) -> str:
    """Plain-text payload of the QR code (kept short so the code stays easy to scan)."""
    allergies = ", ".join(a["substance"] + (f" ({a['reaction']})" if a.get("reaction") else "")
                          for a in summary["allergies"]) or ("NKDA" if summary["no_known_allergies"] else "unknown")
    meds = "; ".join(f"{m['name']} {m.get('dosage') or ''}".strip()
                     for m in summary["current_medications"][:max_items]) or "none recorded"
    conds = ", ".join(c["name"] for c in summary["conditions"][:max_items]) or "none recorded"
    return (f"EMERGENCY MEDICAL CARD\n{patient['full_name']} | DOB {patient['date_of_birth']} | {patient['health_id']}\n"
            f"Blood type: {patient.get('blood_type') or '?'}\nALLERGIES: {allergies}\nMedications: {meds}\n"
            f"Conditions: {conds}\nEmergency contact: {patient.get('emergency_contact') or '?'}\n"
            f"Generated {date.today().isoformat()}")


def _font(size: int, bold: bool = False):
    for path in (f"/usr/share/fonts/truetype/dejavu/DejaVuSans{'-Bold' if bold else ''}.ttf",
                 f"DejaVuSans{'-Bold' if bold else ''}.ttf"):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def _wrap(draw, text: str, font, width: int) -> list[str]:
    lines, line = [], ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if draw.textlength(trial, font=font) <= width:
            line = trial
        else:
            lines.append(line)
            line = word
    return lines + ([line] if line else [])


def render_card(patient: dict, summary: dict) -> bytes:
    """Return the card as PNG bytes (about the proportions of an A6 card)."""
    W, H, pad = 1240, 760, 44
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 96], fill=RED)
    d.text((pad, 26), "EMERGENCY MEDICAL CARD", fill="white", font=_font(40, True))

    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=6, border=2)
    qr.add_data(card_text(patient, summary))
    qr.make(fit=True)
    q = qr.make_image(fill_color="black", back_color="white").convert("RGB").resize((330, 330), Image.NEAREST)
    img.paste(q, (W - 330 - pad, 130))
    d.text((W - 330 - pad, 470), "Scan for the same details", fill=MUTED, font=_font(20))

    x, y, width = pad, 124, W - 330 - 3 * pad
    d.text((x, y), patient["full_name"], fill=DARK, font=_font(42, True)); y += 56
    d.text((x, y), f"DOB {patient['date_of_birth']}  ·  {patient['health_id']}  ·  Blood type "
                   f"{patient.get('blood_type') or '?'}", fill=MUTED, font=_font(24)); y += 50

    def section(title, body, color=DARK, size=27):
        nonlocal y
        d.text((x, y), title, fill=color, font=_font(22, True)); y += 30
        for ln in _wrap(d, body, _font(size, color == RED), width)[:3]:
            d.text((x, y), ln, fill=color, font=_font(size, color == RED)); y += size + 8
        y += 12

    allergies = ", ".join(a["substance"] + (f" ({a['reaction']})" if a.get("reaction") else "")
                          for a in summary["allergies"])
    section("ALLERGIES", allergies or ("No known drug allergies" if summary["no_known_allergies"] else "Unknown"),
            RED if allergies else DARK, 30)
    section("CURRENT MEDICATIONS", "; ".join(f"{m['name']} {m.get('dosage') or ''}".strip()
                                             for m in summary["current_medications"]) or "None recorded")
    section("CONDITIONS", ", ".join(c["name"] for c in summary["conditions"]) or "None recorded")
    d.line([pad, H - 92, W - pad, H - 92], fill=LINE, width=2)
    d.text((pad, H - 76), f"Emergency contact: {patient.get('emergency_contact') or 'not recorded'}",
           fill=DARK, font=_font(24, True))
    d.text((pad, H - 40), f"Generated {date.today().isoformat()} from records at: "
                          + (", ".join(summary["hospitals"]) or "-"), fill=MUTED, font=_font(18))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
