"""
Bulk Email Router
=================
Provides admin-facing endpoints to manage bulk email recipients imported
from CSV and send the Learnogic examiner-outreach email via AWS SES.
Also exposes a public /unsubscribe endpoint used in email footers.
"""

import csv
import io
import time
import logging
from typing import List, Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from ..database import get_db
from ..models import EmailRecipient
from ..schemas import EmailRequest
from ..utils.ses import SESService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/bulk-email", tags=["Bulk Email"])

ses_service = SESService()

# ── Config ────────────────────────────────────────────────────────────────────
FROM_EMAIL   = "info@learnogic.com"
LOGO_URL     = "https://learnogic.s3.ap-south-1.amazonaws.com/static/logo.jpeg"
SUBJECT      = "Examiners as tutors, your edge."
REGISTER_URL = "https://learnogic.com/register-tutor/"
# Base URL for the backend — used to build the unsubscribe link embedded in emails
API_BASE_URL = "https://api.learnogic.com"


# ── Pydantic Schemas ──────────────────────────────────────────────────────────

class RecipientOut(BaseModel):
    id: int
    name: str
    email: str
    is_active: bool
    created_at: Optional[str] = None

    class Config:
        from_attributes = True


class SendResult(BaseModel):
    sent: int
    failed: int
    skipped: int
    total_active: int


class UploadResult(BaseModel):
    added: int
    updated: int
    skipped: int
    total: int


# ── Email Templates ───────────────────────────────────────────────────────────

def build_plain_text(name: str, link: str, unsubscribe_url: str) -> str:
    return (
        f"Dear {name},\n\n"
        "They say the best results come from an \"inside job\", and when it comes to exams, "
        "practicing examiners possess the ultimate assessment insights.\n\n"
        "That's why we've launched a dedicated tutoring space on Learnogic, built exclusively "
        "for current examiners like you to advertise your expertise.\n\n"
        "Unlike other tutoring websites where your expertise can be overshadowed, our platform "
        "ensures your professional insights stand out. Students come to us as they want the "
        "confidence and guidance from assessment specialists who understand the examination system "
        "from the inside. They appreciate the precision, honesty, clarity and depth of "
        "understanding that only active examiners could offer. It is a dedicated environment where "
        "your experience is not just acknowledged — it is the driving force of what makes "
        "Learnogic the leading destination for examiner-led tutoring.\n\n"
        "Why join?\n\n"
        "  * Exclusivity: Stand out on a platform with no competition from non-examiner tutors.\n"
        "  * Targeted audience: Connect directly with students seeking verified current examiners.\n"
        "  * Flexibility: Set your own availability and manage your details easily.\n\n"
        f"Ready to make the most of your expertise? Be part of the community of examiners already "
        f"thriving on the platform — we'd love to welcome you aboard! Don't delay, register today: {link}\n\n"
        "Learnogic Limited\n"
        "Registered address: 167-169 Great Portland Street, London, England, W1W 5PF\n"
        "Registered in England & Wales | Company Registration No. 16130012\n\n"
        f"To unsubscribe from future communications, click here: {unsubscribe_url}\n"
    )


def build_html(name: str, link: str, unsubscribe_url: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Learnogic - For Examiners</title>
  <link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@400;500;700&display=swap" rel="stylesheet">
  <style>body,table,td,p,a,li,span{{font-family:'Montserrat',Arial,sans-serif!important;}}</style>
</head>
<body style="margin:0;padding:0;background-color:#f4f4f4;font-family:'Montserrat',Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background-color:#f4f4f4;padding:30px 0;">
    <tr>
      <td align="center">
        <table width="620" cellpadding="0" cellspacing="0"
               style="background-color:#ffffff;border-radius:8px;overflow:hidden;
                      box-shadow:0 2px 6px rgba(0,0,0,0.08);max-width:620px;">

          <!-- Header / Logo -->
          <tr>
            <td style="padding:30px 40px 20px 40px;border-bottom:1px solid #eeeeee;">
              <img src="{LOGO_URL}" alt="Learnogic" style="height:55px;display:block;">
            </td>
          </tr>

          <!-- Body -->
          <tr>
            <td style="padding:30px 40px;color:#333333;font-size:14px;line-height:1.8;font-family:'Montserrat',Arial,sans-serif;">

              <p style="margin:0 0 16px 0;">
                Dear <span>{name}</span>
              </p>

              <p style="margin:0 0 16px 0;">
                They say the best results come from an &ldquo;inside job&rdquo;, and when it comes
                to exams, practicing examiners possess the ultimate assessment insights.
              </p>

              <p style="margin:0 0 16px 0;">
                That&rsquo;s why we&rsquo;ve launched a dedicated tutoring space on
                <span>Learnogic</span>, built
                <a href="{link}" style="color:#004BAD;font-weight:700;text-decoration:none;">
                  exclusively for current examiners
                </a>
                like you to <em>advertise</em> your expertise.
              </p>

              <p style="margin:0 0 16px 0;">
                Unlike other tutoring websites where your expertise can be overshadowed, our
                platform ensures your professional insights stand out. Students come to us as they
                want the confidence and guidance from assessment specialists who understand the
                examination system from the inside. They appreciate the precision, honesty, clarity
                and depth of understanding that only active examiners could offer. It is a dedicated
                environment where your experience is not just acknowledged &mdash; it is the driving
                force of what makes <span>Learnogic</span> the
                leading destination for examiner-led tutoring.
              </p>

              <!-- Why Join -->
              <p style="margin:24px 0 10px 0;font-size:16px;font-weight:700;color:#e8a020;">
                Why join?
              </p>
              <table cellpadding="0" cellspacing="0" width="100%">
                <tr>
                  <td style="padding:5px 0 5px 12px;font-size:14px;color:#333333;line-height:1.7;">
                    &#9675;&nbsp;&nbsp;<strong>Exclusivity</strong>: Stand out on a platform with
                    no competition from non-examiner tutors.
                  </td>
                </tr>
                <tr>
                  <td style="padding:5px 0 5px 12px;font-size:14px;color:#333333;line-height:1.7;">
                    &#9675;&nbsp;&nbsp;<strong>Targeted audience</strong>: Connect directly with
                    students seeking verified current examiners.
                  </td>
                </tr>
                <tr>
                  <td style="padding:5px 0 5px 12px;font-size:14px;color:#333333;line-height:1.7;">
                    &#9675;&nbsp;&nbsp;<strong>Flexibility</strong>: Set your own availability and
                    manage your details easily.
                  </td>
                </tr>
              </table>

              <p style="margin:20px 0 0 0;">
                Ready to make the most of your expertise? Be part of the community of examiners
                already thriving on the platform &mdash; we&rsquo;d love to welcome you aboard!
                Don&rsquo;t delay, register today:
                <a href="{link}" style="color:#004BAD;font-weight:700;text-decoration:none;">{link}</a>
              </p>

            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="padding:20px 40px 30px 40px;border-top:1px solid #eeeeee;
                       font-size:12px;color:#777777;line-height:1.8;font-family:'Montserrat',Arial,sans-serif;">
              <p style="margin:0;">
                Learnogic Limited<br>
                Registered address: 167-169 Great Portland Street, London, England, W1W 5PF<br>
                Registered in England &amp; Wales | Company Registration No. 16130012
              </p>
              <p style="margin:16px 0 0 0;font-size:11px;color:#999999;">
                If you prefer not to receive future communications from us, click
                <a href="{unsubscribe_url}" style="color:#999999;text-decoration:underline;">here</a>
                to unsubscribe.
              </p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


# ── Helper ────────────────────────────────────────────────────────────────────

def make_unsubscribe_url(email: str) -> str:
    encoded = quote(email, safe="")
    return f"{API_BASE_URL}/bulk-email/unsubscribe?email={encoded}"


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/upload-csv", response_model=UploadResult)
async def upload_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """
    Upload a CSV file with columns: Name, Email address.
    Rows are upserted into the email_recipients table.
    Duplicate emails (already in DB) are updated with the new name.
    """
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are accepted.")

    contents = await file.read()
    text = contents.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))

    added = 0
    updated = 0
    skipped = 0

    for i, row in enumerate(reader, start=2):
        name  = row.get("Name", "").strip()
        email = row.get("Email address", "").strip()

        if not name or not email:
            logger.warning(f"Row {i}: skipping — missing name or email")
            skipped += 1
            continue

        existing = db.query(EmailRecipient).filter(
            EmailRecipient.email == email
        ).first()

        if existing:
            existing.name      = name
            existing.is_active = True   # re-activate if they were unsubscribed and re-imported
            updated += 1
        else:
            db.add(EmailRecipient(name=name, email=email, is_active=True))
            added += 1

    db.commit()

    total = added + updated + skipped
    logger.info(f"CSV upload: added={added}, updated={updated}, skipped={skipped}, total_rows={total}")
    return UploadResult(added=added, updated=updated, skipped=skipped, total=total)


@router.get("/recipients", response_model=List[RecipientOut])
def list_recipients(
    skip: int = 0,
    limit: int = 500,
    db: Session = Depends(get_db)
):
    """Return all recipients with their active/unsubscribed status."""
    recipients = (
        db.query(EmailRecipient)
        .order_by(EmailRecipient.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return [
        RecipientOut(
            id=r.id,
            name=r.name,
            email=r.email,
            is_active=r.is_active,
            created_at=r.created_at.isoformat() if r.created_at else None,
        )
        for r in recipients
    ]


@router.delete("/recipients/{recipient_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_recipient(recipient_id: int, db: Session = Depends(get_db)):
    """Permanently remove a recipient from the database."""
    recipient = db.query(EmailRecipient).filter(
        EmailRecipient.id == recipient_id
    ).first()

    if not recipient:
        raise HTTPException(status_code=404, detail="Recipient not found.")

    db.delete(recipient)
    db.commit()
    return None


@router.post("/send", response_model=SendResult)
def send_bulk_email(
    link: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Send the Learnogic examiner-outreach email to all active recipients.
    Skips unsubscribed (is_active=False) recipients automatically.
    """
    register_link = link or REGISTER_URL

    active_recipients = (
        db.query(EmailRecipient)
        .filter(EmailRecipient.is_active == True)
        .all()
    )

    total_active = len(active_recipients)
    if total_active == 0:
        return SendResult(sent=0, failed=0, skipped=0, total_active=0)

    sent    = 0
    failed  = 0
    skipped = 0

    for idx, r in enumerate(active_recipients):
        unsubscribe_url = make_unsubscribe_url(r.email)

        try:
            email_req = EmailRequest(
                to_addresses=[r.email],
                subject=SUBJECT,
                body_text=build_plain_text(r.name, register_link, unsubscribe_url),
                body_html=build_html(r.name, register_link, unsubscribe_url),
                from_address=FROM_EMAIL,
            )
            ses_service.send_email(email_req)
            sent += 1
            logger.info(f"[{idx+1}/{total_active}] Sent to {r.email}")
        except Exception as e:
            failed += 1
            logger.error(f"[{idx+1}/{total_active}] Failed for {r.email}: {e}")

        # Rate-limit: 0.5 s between sends
        if idx < total_active - 1:
            time.sleep(0.5)

    return SendResult(
        sent=sent,
        failed=failed,
        skipped=skipped,
        total_active=total_active,
    )


@router.get("/unsubscribe", response_class=HTMLResponse)
def unsubscribe(email: str, db: Session = Depends(get_db)):
    """
    Public endpoint — no authentication required.
    Sets is_active=False for the given email address.
    Returns a plain HTML confirmation page.
    """
    recipient = db.query(EmailRecipient).filter(
        EmailRecipient.email == email
    ).first()

    if not recipient:
        return HTMLResponse(
            content=_unsubscribe_page(
                success=False,
                message="We could not find this email address in our list.",
            ),
            status_code=404,
        )

    if not recipient.is_active:
        return HTMLResponse(
            content=_unsubscribe_page(
                success=True,
                message="You have already been unsubscribed from our mailing list.",
            )
        )

    recipient.is_active = False
    db.commit()
    logger.info(f"Unsubscribed: {email}")

    return HTMLResponse(
        content=_unsubscribe_page(
            success=True,
            message="You have been successfully unsubscribed from our mailing list.",
        )
    )


def _unsubscribe_page(success: bool, message: str) -> str:
    colour = "#22c55e" if success else "#ef4444"
    icon   = "✓" if success else "✕"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Unsubscribe — Learnogic</title>
  <link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@400;600&display=swap" rel="stylesheet">
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      background: #f4f4f4;
      font-family: 'Montserrat', sans-serif;
    }}
    .card {{
      background: #fff;
      border-radius: 12px;
      padding: 48px 40px;
      max-width: 480px;
      width: 90%;
      text-align: center;
      box-shadow: 0 4px 24px rgba(0,0,0,0.08);
    }}
    .icon {{
      width: 64px;
      height: 64px;
      border-radius: 50%;
      background: {colour};
      color: #fff;
      font-size: 28px;
      display: flex;
      align-items: center;
      justify-content: center;
      margin: 0 auto 24px;
    }}
    img {{ height: 40px; margin-bottom: 32px; }}
    h1 {{ font-size: 20px; color: #1a1a1a; margin-bottom: 12px; font-weight: 600; }}
    p {{ font-size: 14px; color: #666; line-height: 1.7; }}
    a {{ color: #004BAD; text-decoration: none; font-weight: 600; }}
  </style>
</head>
<body>
  <div class="card">
    <img src="{LOGO_URL}" alt="Learnogic">
    <div class="icon">{icon}</div>
    <h1>{"Success" if success else "Not Found"}</h1>
    <p>{message}</p>
    <p style="margin-top:24px;">
      <a href="https://learnogic.com">Return to Learnogic &rarr;</a>
    </p>
  </div>
</body>
</html>"""
