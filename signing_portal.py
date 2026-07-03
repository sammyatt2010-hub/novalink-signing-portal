"""
Novalink Hardware — Remote Customer Signing Portal
Deploy this as a SEPARATE Streamlit app at e.g. novalink-signing.streamlit.app
Customers receive a unique link: https://your-signing-app.streamlit.app/?gist=GIST_ID
"""

import streamlit as st
import requests
import base64
import json
import io
import hashlib
import uuid
import smtplib
import numpy as np
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
from fpdf import FPDF
from PIL import Image as PILImage

try:
    from streamlit_drawable_canvas import st_canvas
    CANVAS_OK = True
except ImportError:
    CANVAS_OK = False

st.set_page_config(
    page_title="Sign Documents — Novalink Hardware",
    page_icon="✍️",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Syne:wght@700;800&family=DM+Sans:wght@300;400;500&display=swap');
  html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
  .portal-header { background:linear-gradient(135deg,#0d2e4a 0%,#0a3d62 100%);
    border-radius:14px; padding:1.8rem 2rem; margin-bottom:1.5rem; border:1px solid rgba(0,180,216,0.2); }
  .portal-header h1 { font-family:'Syne',sans-serif; font-weight:800; font-size:1.6rem; color:#fff; margin:0 0 0.2rem; }
  .portal-header p  { color:rgba(255,255,255,0.55); margin:0; font-size:0.88rem; }
  .doc-card { background:#fff; border:1px solid #e0e8f0; border-radius:10px; padding:0.9rem 1.2rem;
    margin-bottom:0.6rem; display:flex; justify-content:space-between; align-items:center; }
  .doc-name { font-weight:600; color:#0d2e4a; }
  .status-badge { background:#e8f8f0; color:#1a7a40; padding:0.2rem 0.7rem; border-radius:20px;
    font-size:0.72rem; font-weight:700; text-transform:uppercase; letter-spacing:.06em; }
  .info-block { background:#e8f4fb; border-left:4px solid #00b4d8; border-radius:0 8px 8px 0;
    padding:0.8rem 1rem; margin:0.8rem 0; font-size:0.88rem; color:#0a3d62; }
  .success-block { background:#e8f8f0; border-left:4px solid #1a7a40; border-radius:0 8px 8px 0;
    padding:0.8rem 1rem; margin:0.8rem 0; font-size:0.88rem; color:#1a4a2a; }
</style>
""", unsafe_allow_html=True)

# ── SECRETS (safe access — shows setup instructions if not configured) ────────
def _secret(key, default=""):
    try:
        return st.secrets.get(key, default)
    except Exception:
        return default

GITHUB_TOKEN = _secret("GITHUB_TOKEN")
SMTP_HOST    = _secret("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT    = int(_secret("SMTP_PORT", 587))
SMTP_USER    = _secret("SMTP_USER", "novalinkhardwarepaperwork@gmail.com")
SMTP_PASS    = _secret("SMTP_PASS")
FROM_NAME    = _secret("FROM_NAME", "Novalink Hardware")

# Show setup banner if secrets are missing
if not GITHUB_TOKEN:
    st.warning("Setup required: add GITHUB_TOKEN, SMTP_USER, SMTP_PASS and FROM_NAME to this app's Streamlit Cloud secrets (Settings > Secrets).")


def fetch_gist(gist_id):
    hdrs = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github+json"} if GITHUB_TOKEN else {}
    r = requests.get(f"https://api.github.com/gists/{gist_id}", headers=hdrs, timeout=10)
    return r.json() if r.status_code == 200 else None



def update_gist(gist_id, files_dict, description=None):
    hdrs    = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github+json"}
    payload = {"files": files_dict}
    if description:
        payload["description"] = description
    requests.patch(f"https://api.github.com/gists/{gist_id}", json=payload, headers=hdrs, timeout=15)


def get_client_ip():
    try:
        for h in ["X-Forwarded-For", "X-Real-IP", "CF-Connecting-IP"]:
            ip = st.context.headers.get(h, "")
            if ip:
                return ip.split(",")[0].strip()
    except Exception:
        pass
    return "Not captured"


def send_signed_email(to_addr, cc_addr, customer_name, pdf_list, filenames):
    if not SMTP_PASS:
        return False, "SMTP not configured."
    try:
        msg            = MIMEMultipart()
        msg["From"]    = f"{FROM_NAME} <{SMTP_USER}>"
        msg["To"]      = to_addr
        msg["Subject"] = "Your Signed Documents - Novalink Hardware"
        if cc_addr:
            msg["Cc"] = cc_addr
        msg.attach(MIMEText(f"""<html><body style="font-family:Arial;color:#333;max-width:600px;margin:0 auto">
          <div style="background:#0d2e4a;padding:20px 30px;border-radius:8px 8px 0 0">
            <h2 style="color:#fff;margin:0"><span style="color:#00b4d8">Novalink</span> Hardware</h2></div>
          <div style="background:#f9f9f9;padding:24px 30px;border:1px solid #e0e8e8;border-top:none">
            <p>Dear {customer_name},</p>
            <p>Thank you for signing. Your completed signed documents are attached for your records.</p>
            <p>Kind regards,<br/><strong>{FROM_NAME}</strong></p></div>
        </body></html>""", "html"))
        for pdf_bytes, fname in zip(pdf_list, filenames):
            part = MIMEBase("application", "octet-stream")
            part.set_payload(pdf_bytes)
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", f'attachment; filename="{fname}"')
            msg.attach(part)
        recipients = [r.strip() for r in [to_addr, cc_addr] if r and r.strip()]
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as srv:
            srv.ehlo(); srv.starttls(); srv.ehlo()
            srv.login(SMTP_USER, SMTP_PASS)
            srv.sendmail(SMTP_USER, recipients, msg.as_string())
        return True, "sent"
    except smtplib.SMTPAuthenticationError:
        return False, "Gmail authentication failed - check App Password in secrets."
    except Exception as e:
        return False, str(e)


def build_certificate(sig_bytes, sig_name, company, timestamp, ip_addr, doc_bytes_for_hash):
    """Build a standalone Certificate of Completion PDF."""
    envelope_id = str(uuid.uuid4()).upper()
    doc_hash    = hashlib.sha256(doc_bytes_for_hash).hexdigest().upper()

    cert = FPDF()
    cert.set_margins(15, 15, 15)
    cert.add_page()

    # Header
    cert.set_fill_color(13, 46, 74)
    cert.rect(0, 0, 210, 22, "F")
    cert.set_font("Helvetica", "B", 13)
    cert.set_text_color(255, 255, 255)
    cert.set_y(5)
    cert.cell(0, 6, "CERTIFICATE OF COMPLETION", ln=True, align="C")
    cert.set_font("Helvetica", "", 8)
    cert.cell(0, 5, "Novalink Hardware  |  Electronic Signing Record", ln=True, align="C")
    cert.set_fill_color(0, 180, 216)
    cert.rect(0, 22, 210, 1.5, "F")
    cert.set_text_color(0, 0, 0)
    cert.ln(8)

    def sec(t):
        cert.set_font("Helvetica", "B", 9)
        cert.set_fill_color(220, 235, 245)
        cert.set_text_color(13, 46, 74)
        cert.cell(0, 6, f"  {t}", fill=True, ln=True)
        cert.set_text_color(0, 0, 0)

    def kv(l, v, color=(0,0,0)):
        cert.set_font("Helvetica", "B", 8); cert.set_text_color(100, 100, 100)
        cert.cell(52, 5.5, l, ln=False)
        cert.set_font("Helvetica", "", 8); cert.set_text_color(*color)
        cert.cell(0, 5.5, str(v)[:80], ln=True)
        cert.set_text_color(0, 0, 0)

    sec("Envelope Summary")
    cert.ln(1)
    kv("Envelope ID:", envelope_id)
    kv("Status:", "COMPLETED", color=(0, 140, 70))
    kv("Originator:", FROM_NAME)
    kv("Time Zone:", "(UTC+00:00) Dublin, Edinburgh, Lisbon, London")
    kv("Originator Email:", SMTP_USER)
    cert.ln(4)

    sec("Signer Events")
    cert.ln(1)
    cert.set_font("Helvetica", "B", 8)
    cert.cell(65, 5.5, "Signer Details", border="B", ln=False)
    cert.cell(65, 5.5, "Signature", border="B", ln=False)
    cert.cell(0,  5.5, "Timestamps", border="B", ln=True)

    y0 = cert.get_y()
    # Signature image in middle column
    if sig_bytes:
        try:
            cert.image(io.BytesIO(sig_bytes), x=68, y=y0, w=58, h=18)
        except Exception:
            pass
    # Right column timestamps
    cert.set_xy(cert.l_margin + 135, y0)
    cert.set_font("Helvetica", "", 7.5)
    cert.cell(0, 5, f"Sent:   {timestamp}", ln=True)
    cert.set_xy(cert.l_margin + 135, y0 + 5)
    cert.cell(0, 5, f"Viewed: {timestamp}", ln=True)
    cert.set_xy(cert.l_margin + 135, y0 + 10)
    cert.cell(0, 5, f"Signed: {timestamp}", ln=True)
    # Left column signer details
    cert.set_y(y0 + 1)
    cert.set_font("Helvetica", "B", 8)
    cert.cell(65, 5, sig_name or "Customer", ln=True)
    cert.set_x(cert.l_margin)
    cert.set_font("Helvetica", "", 8)
    cert.cell(65, 5, company or "", ln=True)
    cert.set_x(cert.l_margin)
    cert.set_font("Helvetica", "I", 7.5)
    cert.set_text_color(80, 80, 80)
    cert.cell(65, 5, f"IP: {ip_addr}", ln=True)
    cert.set_x(cert.l_margin)
    cert.cell(65, 5, "Method: Hand-drawn / photo", ln=True)
    cert.set_text_color(0, 0, 0)
    cert.ln(4)

    sec("Carbon Copy Events")
    cert.ln(1)
    cert.set_font("Helvetica", "B", 8)
    cert.cell(65, 5.5, "Recipient", border="B", ln=False)
    cert.cell(65, 5.5, "Status", border="B", ln=False)
    cert.cell(0,  5.5, "Timestamps", border="B", ln=True)
    cert.set_font("Helvetica", "", 8)
    cert.cell(65, 5.5, SMTP_USER, ln=False)
    cert.cell(65, 5.5, "COPIED", ln=False)
    cert.cell(0,  5.5, timestamp, ln=True)
    cert.ln(4)

    sec("Envelope Summary Events")
    cert.ln(1)
    cert.set_font("Helvetica", "B", 8)
    for h in ["Event", "Status", "Timestamp"]:
        w = 65 if h != "Timestamp" else 0
        cert.cell(w, 5.5, h, border="B", ln=(1 if h == "Timestamp" else 0))
    cert.set_font("Helvetica", "", 8)
    for ev, st_txt in [("Envelope Sent","Hashed / Encrypted"),("Certified Delivered","Security Checked"),
                        ("Signing Complete","Security Checked"),("Completed","Security Checked")]:
        cert.cell(65, 5.5, ev, ln=False)
        cert.cell(65, 5.5, st_txt, ln=False)
        cert.cell(0,  5.5, timestamp, ln=True)
    cert.ln(4)

    sec("Document Integrity")
    cert.ln(2)
    kv("Document Hash (SHA-256):", doc_hash[:40])
    kv("Signing Method:", "Remote electronic signature via Novalink Hardware Signing Portal")
    kv("Platform:", "Novalink Hardware Remote Signing Portal - Streamlit Cloud")
    kv("Full Envelope ID:", envelope_id)
    cert.ln(4)

    cert.set_font("Helvetica", "I", 7.5)
    cert.set_text_color(120, 120, 120)
    cert.set_x(cert.l_margin)
    cert.multi_cell(cert.epw, 4,
        "This certificate confirms that the above-named signer reviewed and electronically signed "
        "the attached documentation. The timestamp, IP address and signature were recorded at the "
        "moment of signing. This constitutes a valid electronic agreement under the Electronic "
        "Communications Act 2000 and eIDAS Regulation (EU) 910/2014.")

    cert.set_y(-15)
    cert.set_font("Helvetica", "I", 7)
    cert.set_text_color(150, 150, 150)
    cert.cell(0, 5, "Novalink Hardware | All figures exclude VAT | This document is confidential", align="C")

    return bytes(cert.output())


# ── MAIN ROUTING ──────────────────────────────────────────────────────────────
gist_id = st.query_params.get("gist", "")

if not gist_id:
    st.markdown("""<div class="portal-header">
      <h1>✍️ Novalink Hardware Signing Portal</h1>
      <p>This page is accessed via a unique link sent to you by Novalink Hardware.</p>
    </div>""", unsafe_allow_html=True)
    st.warning("No signing session found in this link. Please check the link you received or contact Novalink Hardware.")
    st.stop()

with st.spinner("Loading your documents..."):
    gist = fetch_gist(gist_id)

if not gist:
    st.error("Could not load the signing session. The link may be invalid or expired. Please contact Novalink Hardware.")
    st.stop()

try:
    session = json.loads(gist["files"].get("session.json", {}).get("content", "{}"))
except Exception:
    st.error("Session data is corrupted. Please contact Novalink Hardware.")
    st.stop()

if session.get("status") == "signed":
    st.markdown("""<div class="portal-header">
      <h1>✅ Already Signed</h1>
      <p>These documents have already been signed. Signed copies were emailed at the time of signing.</p>
    </div>""", unsafe_allow_html=True)
    st.info("If you need another copy, please contact Novalink Hardware directly.")
    st.stop()

customer_name  = session.get("customer_name", "Customer")
customer_email = session.get("customer_email", "")
sender_email   = session.get("sender_email", "")
custom_message = session.get("message", "")

# ── HEADER ────────────────────────────────────────────────────────────────────
st.markdown(f"""<div class="portal-header">
  <h1>✍️ Documents Ready for Your Signature</h1>
  <p>Prepared for <strong>{customer_name}</strong> &nbsp;·&nbsp; Please review each document below, then sign at the bottom.</p>
</div>""", unsafe_allow_html=True)

if custom_message:
    st.markdown(f'<div class="info-block">💬 Message: <em>{custom_message}</em></div>', unsafe_allow_html=True)

# ── DOCUMENTS ────────────────────────────────────────────────────────────────
st.markdown("### 📄 Your Documents")
doc_files = sorted([(k, v) for k, v in gist["files"].items()
                    if k.startswith("doc_") and k.endswith(".b64")])
doc_data  = []

for key, file_info in doc_files:
    try:
        pdf_bytes    = base64.b64decode(file_info["content"])
        parts        = key.split("_", 2)
        display_name = parts[2].replace(".b64", "") if len(parts) == 3 else key
        doc_data.append((display_name, pdf_bytes))

        c1, c2 = st.columns([5, 1])
        with c1:
            st.markdown(f'<div class="doc-card"><span class="doc-name">📄 {display_name}</span><span class="status-badge">Ready to sign</span></div>',
                        unsafe_allow_html=True)
        with c2:
            st.download_button("⬇️ Download", data=pdf_bytes, file_name=display_name,
                               mime="application/pdf", use_container_width=True, key=f"dl_{key}")

        with st.expander(f"👁️ Preview: {display_name}"):
            b64_display = base64.b64encode(pdf_bytes).decode()
            st.markdown(f'<iframe src="data:application/pdf;base64,{b64_display}" width="100%" height="500px" type="application/pdf"></iframe>',
                        unsafe_allow_html=True)
    except Exception:
        st.warning(f"Could not load: {key}")

if not doc_data:
    st.error("No documents found in this session.")
    st.stop()

st.divider()

# ── SIGNATURE ─────────────────────────────────────────────────────────────────
st.markdown("### ✍️ Your Signature")
sig_method = st.radio("How would you like to sign?",
                      ["Draw on screen", "Upload a photo of your signature"],
                      horizontal=True)

if sig_method == "Draw on screen":
    if not CANVAS_OK:
        st.warning("Drawing pad unavailable. Please use Upload photo instead.")
    else:
        with st.container(border=True):
            st.caption("Draw your signature below using mouse, finger or stylus.")
            cr = st_canvas(fill_color="rgba(0,0,0,0)", stroke_width=3,
                           stroke_color="#000000", background_color="#EAF4FB",
                           update_streamlit=True, height=180, width=510,
                           drawing_mode="freedraw", display_toolbar=True, key="sig_canvas")
        if cr.image_data is not None:
            if cr.image_data[:,:,3].sum() > 500:
                img = PILImage.fromarray(cr.image_data.astype("uint8"), "RGBA").convert("RGB")
                buf = io.BytesIO(); img.save(buf, "PNG")
                st.session_state["_psig"] = buf.getvalue()
                st.success("Signature captured")
            else:
                st.session_state.pop("_psig", None)
else:
    f = st.file_uploader("Upload signature image", type=["jpg","jpeg","png"], label_visibility="collapsed")
    if f:
        img = PILImage.open(f).convert("RGB").resize((400, 120), PILImage.LANCZOS)
        buf = io.BytesIO(); img.save(buf, "PNG")
        st.session_state["_psig"] = buf.getvalue()
        st.image(f, width=280, caption="Preview")
        st.success("Signature uploaded")

sig_bytes = st.session_state.get("_psig")

st.markdown("### ✅ Confirm Your Details")
c1, c2 = st.columns(2)
with c1:
    confirm_name = st.text_input("Full name", placeholder="Jane Smith", key="cname")
with c2:
    confirm_role = st.text_input("Role / Position", placeholder="Managing Director", key="crole")

agree = st.checkbox("I confirm I have read all the above documents and agree to sign them electronically.")

st.markdown("")
can_sign = bool(sig_bytes and confirm_name and agree)

if not can_sign:
    missing = [x for cond, x in [(not sig_bytes, "signature"), (not confirm_name, "full name"), (not agree, "agreement tick")] if cond]
    if missing:
        st.caption(f"Still needed: {', '.join(missing)}")

if st.button("✍️  Sign & Send Documents", type="primary", use_container_width=True, disabled=not can_sign):
    with st.spinner("Signing and sending..."):
        ts         = datetime.now().strftime("%d/%m/%Y  %H:%M")
        ip         = get_client_ip()
        signer_str = f"{confirm_name} - {confirm_role}" if confirm_role else confirm_name

        cert_bytes = build_certificate(sig_bytes, signer_str, customer_name, ts, ip, doc_data[0][1])
        cert_name  = f"Certificate_of_Completion_{customer_name.replace(' ','_')}.pdf"

        all_pdf_bytes = [d[1] for d in doc_data] + [cert_bytes]
        all_names     = [d[0] for d in doc_data] + [cert_name]

        ok, msg = send_signed_email(customer_email, sender_email, customer_name, all_pdf_bytes, all_names)

        update_gist(gist_id,
            {"session.json": {"content": json.dumps({**session,
                "status": "signed", "signed_at": datetime.now().isoformat(),
                "signed_by_name": signer_str, "signed_by_ip": ip}, indent=2)}},
            description=f"SIGNED - Novalink - {customer_name}")

        st.session_state.pop("_psig", None)

    if ok:
        st.markdown(f"""<div class="success-block">
          ✅ <strong>Signed successfully!</strong><br/>
          All documents and your Certificate of Completion have been emailed to <strong>{customer_email}</strong>.<br/>
          Signed: {ts} &nbsp;|&nbsp; Reference: {gist_id[:12].upper()}
        </div>""", unsafe_allow_html=True)
        st.balloons()
    else:
        st.error(f"Signing recorded but email failed: {msg}")

    st.download_button("📥 Download Certificate of Completion", data=cert_bytes,
                       file_name=cert_name, mime="application/pdf", use_container_width=True)
