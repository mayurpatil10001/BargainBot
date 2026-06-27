# -*- coding: utf-8 -*-
"""
BargainBot - emailer.py
Sends HTML price-alert emails via Gmail SMTP SSL.
Uses only smtplib and email.mime (Python built-ins - no pip install needed).
"""

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

try:
    from email_config import GMAIL_SENDER, GMAIL_APP_PASSWORD
except ImportError:
    GMAIL_SENDER       = ""
    GMAIL_APP_PASSWORD = ""


def send_price_alert_email(
    recipient_email: str,
    product_name: str,
    current_price: int,
    target_price: int,
    platform: str,
    predicted_price: int,
    days_to_wait: int,
    savings: int,
    why_explanation: str,
) -> bool:
    """
    Sends an HTML price-drop alert email to the recipient.

    Returns:
        True  if the email was sent successfully.
        False if sending failed (error printed to console).
    """
    try:
        subject = f"Price Drop Alert \u2014 {product_name} is now \u20b9{current_price:,}"

        # Build the platform shop URL fragments
        platform_name  = platform.capitalize()
        platform_color = "#2563EB"

        html_body = f"""
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{subject}</title>
</head>
<body style="margin:0;padding:0;background:#F8FAFC;font-family:'Segoe UI',Arial,sans-serif;">

  <!-- Wrapper -->
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#F8FAFC;padding:40px 16px;">
    <tr>
      <td align="center">
        <table width="560" cellpadding="0" cellspacing="0"
               style="max-width:560px;width:100%;background:#FFFFFF;
                      border:1px solid #E2E8F0;border-radius:16px;
                      overflow:hidden;">

          <!-- Header -->
          <tr>
            <td style="background:#2563EB;padding:28px 36px;">
              <p style="margin:0;font-size:22px;font-weight:700;
                         color:#FFFFFF;letter-spacing:-0.3px;">BargainBot</p>
              <p style="margin:6px 0 0;font-size:14px;
                         color:rgba(255,255,255,0.75);">
                Your price alert was triggered
              </p>
            </td>
          </tr>

          <!-- Body -->
          <tr>
            <td style="padding:32px 36px;">

              <!-- Badge -->
              <div style="text-align:center;margin-bottom:24px;">
                <span style="display:inline-block;
                             background:#F0FDF4;color:#15803D;
                             border:1px solid #BBF7D0;border-radius:8px;
                             padding:10px 20px;font-size:15px;font-weight:700;">
                  &#10003; Price Drop Detected
                </span>
              </div>

              <!-- Product name -->
              <p style="margin:0 0 20px;font-size:16px;font-weight:600;
                         color:#0F172A;text-align:center;">
                {product_name}
              </p>

              <!-- Price rows -->
              <table width="100%" cellpadding="0" cellspacing="0">
                <tr>
                  <td style="border-bottom:1px solid #F1F5F9;padding:14px 0;">
                    <span style="font-size:14px;color:#64748B;">Current Price</span>
                  </td>
                  <td style="border-bottom:1px solid #F1F5F9;padding:14px 0;
                              text-align:right;">
                    <span style="font-size:18px;font-weight:700;color:#16A34A;">
                      &#8377;{current_price:,}
                    </span>
                  </td>
                </tr>
                <tr>
                  <td style="border-bottom:1px solid #F1F5F9;padding:14px 0;">
                    <span style="font-size:14px;color:#64748B;">Your Target Price</span>
                  </td>
                  <td style="border-bottom:1px solid #F1F5F9;padding:14px 0;
                              text-align:right;">
                    <span style="font-size:18px;font-weight:700;color:#0F172A;">
                      &#8377;{target_price:,}
                    </span>
                  </td>
                </tr>
                <tr>
                  <td style="border-bottom:1px solid #F1F5F9;padding:14px 0;">
                    <span style="font-size:14px;color:#64748B;">Predicted Price (soon)</span>
                  </td>
                  <td style="border-bottom:1px solid #F1F5F9;padding:14px 0;
                              text-align:right;">
                    <span style="font-size:18px;font-weight:700;color:#0F172A;">
                      &#8377;{predicted_price:,}
                    </span>
                  </td>
                </tr>
                <tr>
                  <td style="border-bottom:1px solid #F1F5F9;padding:14px 0;">
                    <span style="font-size:14px;color:#64748B;">Best Platform</span>
                  </td>
                  <td style="border-bottom:1px solid #F1F5F9;padding:14px 0;
                              text-align:right;">
                    <span style="font-size:18px;font-weight:700;color:#0F172A;">
                      {platform_name}
                    </span>
                  </td>
                </tr>
              </table>

              <!-- Savings box -->
              <div style="background:#F0FDF4;border:1px solid #BBF7D0;
                           border-radius:12px;padding:20px 24px;
                           margin:24px 0;text-align:center;">
                <p style="margin:0;font-size:32px;font-weight:800;color:#16A34A;">
                  &#8377;{savings:,}
                </p>
                <p style="margin:6px 0 0;font-size:13px;color:#64748B;">
                  Total savings vs. target price
                </p>
              </div>

              <!-- Info rows -->
              <p style="font-size:14px;color:#64748B;margin:12px 0;">
                <strong style="color:#0F172A;">When to buy:</strong>&nbsp;
                {"Now - the price has dropped to your target!" if days_to_wait <= 1
                  else f"Within {days_to_wait} days for best savings"}
              </p>
              <p style="font-size:14px;color:#64748B;margin:12px 0;">
                <strong style="color:#0F172A;">Why this drop:</strong>&nbsp;
                {why_explanation}
              </p>
              <p style="font-size:14px;color:#64748B;margin:12px 0;">
                <strong style="color:#0F172A;">Best platform:</strong>&nbsp;
                {platform_name} at &#8377;{current_price:,}
              </p>

              <!-- CTA Button -->
              <a href="https://www.{platform_name.lower()}.{'in' if platform_name.lower() == 'amazon' else 'com'}/s?k={product_name.replace(' ', '+')}"
                 style="display:block;background:#2563EB;color:#FFFFFF;
                         text-align:center;padding:16px;border-radius:10px;
                         font-size:16px;font-weight:600;margin-top:28px;
                         text-decoration:none;">
                Shop Now on {platform_name} &rarr;
              </a>

            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="background:#F8FAFC;border-top:1px solid #E2E8F0;
                        padding:20px 36px;text-align:center;
                        font-size:12px;color:#94A3B8;">
              &copy; 2025 BargainBot &mdash; Smart shopping for India<br/>
              <span style="font-size:11px;">
                You received this because you set a price alert on BargainBot.
              </span>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>

</body>
</html>
"""

        # Compose the message
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = GMAIL_SENDER
        msg["To"]      = recipient_email

        plain_text = (
            f"BargainBot Price Drop Alert\n\n"
            f"Good news! {product_name} is now \u20b9{current_price:,} on {platform_name}.\n"
            f"Your target price was: \u20b9{target_price:,}\n"
            f"Total savings: \u20b9{savings:,}\n\n"
            f"Why: {why_explanation}\n\n"
            f"Happy shopping!\n\u00a9 2025 BargainBot"
        )

        msg.attach(MIMEText(plain_text, "plain"))
        msg.attach(MIMEText(html_body, "html"))

        # Send via Gmail SMTP SSL
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_SENDER, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_SENDER, recipient_email, msg.as_string())

        print(f"[Email] Alert sent to {recipient_email} for '{product_name}'")
        return True

    except Exception as e:
        print(f"[Email] Failed to send alert to {recipient_email}: {e}")
        return False
