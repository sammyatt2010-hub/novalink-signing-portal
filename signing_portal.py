"""
SY Comms — Remote Signing Portal
A standalone Streamlit app that lets customers review and sign their proposal
without needing to be in the room. Deal data is passed via a GitHub Gist ID
in the URL query parameter.
"""
import streamlit as st
import requests, json, base64, io, tempfile, os
from datetime import date

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="SY Comms — Sign Your Proposal",
    page_icon="✍️",
    layout="centered",
)

# ── Branding ──────────────────────────────────────────────────────────────────
BRAND_PURPLE = "#1f1450"
BRAND_TEAL   = "#00b5a3"

st.markdown(f"""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;700;800&display=swap');
  html, body, [class*="css"] {{ font-family: 'Syne', sans-serif; }}
  .sy-header {{
      background: {BRAND_PURPLE};
      color: white;
      padding: 1.5rem 2rem;
      border-radius: 12px;
      margin-bottom: 1.5rem;
  }}
  .sy-header h1 {{ margin:0; font-size:1.8rem; font-weight:800; }}
  .sy-header p  {{ margin:0.3rem 0 0 0; color:{BRAND_TEAL}; font-size:0.95rem; }}
  .sy-card {{
      background:#f8f9ff;
      border-radius:10px;
      padding:1.2rem 1.5rem;
      margin-bottom:1rem;
      border-left:4px solid {BRAND_TEAL};
  }}
  .sy-label {{font-size:0.75rem;font-weight:700;text-transform:uppercase;
              letter-spacing:.08em;color:#aaa;margin-bottom:0.3rem}}
  .sy-value {{font-size:1.1rem;font-weight:700;color:{BRAND_PURPLE}}}
  .sy-footer {{text-align:center;color:#aaa;font-size:0.75rem;margin-top:2rem;padding-top:1rem;
               border-top:1px solid #eee}}
</style>
<div class="sy-header">
  <h1>✍️ SY Comms — Sign Your Proposal</h1>
  <p>hello@sycomms.co.uk &nbsp;·&nbsp; 01743 667419 &nbsp;·&nbsp; www.sycomms.co.uk</p>
</div>
""", unsafe_allow_html=True)

# ── Load deal data from Gist ──────────────────────────────────────────────────
params = st.query_params
gist_id = params.get("gist", "")

if not gist_id:
    st.warning("No proposal link found. Please use the link provided by your SY Comms consultant.")
    st.stop()

@st.cache_data(ttl=300)
def load_gist(gid, token=""):
    """Fetch deal data from a private GitHub Gist."""
    hdrs = {"Authorization": f"token {token}", "Accept": "application/vnd.github+json"} if token else {}
    try:
        r = requests.get(f"https://api.github.com/gists/{gid}", headers=hdrs, timeout=15)
    except Exception as e:
        return None, f"Network error: {e}"
    if r.status_code == 404:
        return None, "Gist not found — link may have expired."
    if r.status_code == 401:
        return None, "Authentication error — portal not configured correctly."
    if r.status_code != 200:
        return None, f"GitHub error {r.status_code}"
    files = r.json().get("files", {})
    # Prefer session.json
    for fname in ("session.json",):
        if fname in files:
            raw = files[fname]
            if raw.get("truncated"):
                r2 = requests.get(raw["raw_url"], headers=hdrs, timeout=15)
                return json.loads(r2.text), None
            return json.loads(raw["content"]), None
    # Fallback: any JSON file
    for fname, fdata in files.items():
        if fname.endswith(".json"):
            return json.loads(fdata["content"]), None
    return None, "No deal data found in this link."

# Read token outside the cached function
_gh_token = ""
if hasattr(st, "secrets"):
    try:
        _gh_token = st.secrets.get("GITHUB_TOKEN", "")
    except Exception:
        pass

with st.spinner("Loading your proposal…"):
    deal, _err = load_gist(gist_id, token=_gh_token)

if deal is None:
    st.error(f"Could not load proposal: {_err or 'Link may have expired.'} "
             "Please contact your SY Comms consultant on 01743 667419.")
    if not _gh_token:
        st.warning("⚙️ Portal not yet configured — GITHUB_TOKEN missing from Streamlit secrets.")
    st.stop()

# ── Pull key deal values ──────────────────────────────────────────────────────
comp_name    = deal.get("comp_name", deal.get("customer_name", ""))
contact      = deal.get("contact_name", deal.get("customer_name", ""))
total_mo     = float(deal.get("total_mo", 0.0))
hw_rental    = float(deal.get("hw_monthly_spread", 0.0))
svc_total    = float(deal.get("svc_total_sell", 0.0))
lease_months = int(deal.get("lease_term", 84))
lease_label  = deal.get("lease_label", f"{lease_months} months")
install_type = deal.get("install_type", "")
bb_info      = f"{deal.get('bb_provider','')} {deal.get('bb_package','')}".strip()
address      = deal.get("install_address", "")
pdf_b64      = deal.get("pdf_b64", "")

st.markdown(f"### Welcome, {contact or comp_name or 'there'} 👋")
st.markdown(
    f"Your SY Comms consultant has prepared a proposal for **{comp_name}**. "
    "Please review the key details below and sign to confirm your agreement."
)

# ── Key figures ───────────────────────────────────────────────────────────────
col1, col2, col3 = st.columns(3)
with col1:
    st.markdown(f"""<div class="sy-card">
      <div class="sy-label">Monthly Lease</div>
      <div class="sy-value">£{hw_rental:.2f}/mo</div>
      <div style="font-size:0.78rem;color:#aaa">Hardware + VAT</div>
    </div>""", unsafe_allow_html=True)
with col2:
    st.markdown(f"""<div class="sy-card">
      <div class="sy-label">Monthly Services</div>
      <div class="sy-value">£{svc_total:.2f}/mo</div>
      <div style="font-size:0.78rem;color:#aaa">{bb_info if bb_info else "Licences + BB + VAT"}</div>
    </div>""", unsafe_allow_html=True)
with col3:
    st.markdown(f"""<div class="sy-card">
      <div class="sy-label">Agreement Term</div>
      <div class="sy-value">{lease_label}</div>
      <div style="font-size:0.78rem;color:#aaa">{install_type}</div>
    </div>""", unsafe_allow_html=True)

# ── Download proposal PDF if included ────────────────────────────────────────
if pdf_b64:
    pdf_bytes = base64.b64decode(pdf_b64)
    st.download_button(
        "📄 Download Your Proposal (PDF)",
        data=pdf_bytes,
        file_name=f"SYComms_Proposal_{comp_name.replace(' ','_')}.pdf",
        mime="application/pdf",
        use_container_width=True,
    )
    st.markdown("---")

# ── Signature capture ─────────────────────────────────────────────────────────
st.markdown("### ✍️ Sign Below to Confirm")
st.caption(
    "By signing below, I/we confirm I have read and agree to the proposal and "
    "SY Comms Terms & Conditions (https://sycomms.co.uk/terms-conditions)."
)

sig_name_rs = st.text_input("Full Name", placeholder="Jane Smith", key="rs_sig_name")
sig_pos_rs  = st.text_input("Position / Title", placeholder="Director", key="rs_sig_pos")

try:
    from streamlit_drawable_canvas import st_canvas
    canvas_result = st_canvas(
        fill_color="rgba(0,0,0,0)",
        stroke_width=3,
        stroke_color="#1f1450",
        background_color="#f8f9ff",
        update_streamlit=True,
        return_image_data=True,
        height=160,
        width=680,
        drawing_mode="freedraw",
        key="rs_canvas",
    )
    canvas_ok = True
except Exception:
    canvas_ok = False
    st.info("Signature pad unavailable — please upload a photo of your signature below.")

sig_upload_rs = st.file_uploader("Or upload signature image", type=["png","jpg","jpeg"],
                                  key="rs_sig_upload", label_visibility="collapsed")

# Save signature bytes
sig_bytes_rs = st.session_state.get("_rs_sig_bytes")

_rs_btn_col, _rs_clr_col = st.columns(2)
with _rs_btn_col:
    if st.button("✅ Confirm Signature", use_container_width=True, type="primary", key="rs_save_sig"):
        _saved = False
        # Try canvas first
        if canvas_ok:
            try:
                _img = canvas_result.image_data if canvas_result else None
                if _img is not None:
                    from PIL import Image as _PILImage
                    _white = _PILImage.new("RGBA", (_img.shape[1], _img.shape[0]), (255,255,255,255))
                    _white.paste(_PILImage.fromarray(_img.astype("uint8"), "RGBA"),
                                 mask=_PILImage.fromarray(_img.astype("uint8"), "RGBA").split()[3])
                    _buf = io.BytesIO()
                    _white.convert("RGB").save(_buf, format="PNG")
                    st.session_state["_rs_sig_bytes"] = _buf.getvalue()
                    _saved = True
            except Exception:
                pass
        # Fallback to upload
        if not _saved and sig_upload_rs:
            st.session_state["_rs_sig_bytes"] = sig_upload_rs.read()
            _saved = True
        if _saved:
            sig_bytes_rs = st.session_state["_rs_sig_bytes"]
            st.rerun()
        else:
            st.warning("Please draw or upload a signature first.")
with _rs_clr_col:
    if st.button("🗑️ Clear", use_container_width=True, key="rs_clr"):
        st.session_state.pop("_rs_sig_bytes", None)
        st.rerun()

if sig_bytes_rs:
    st.success("✅ Signature confirmed")
    try:
        st.image(sig_bytes_rs, width=250, caption="Your signature")
    except Exception:
        pass

# ── Submit ────────────────────────────────────────────────────────────────────
st.markdown("---")
_ready = bool(sig_bytes_rs and sig_name_rs)
if not _ready:
    st.caption("Please complete your name and signature above to submit.")

def _build_receipt_pdf(comp, signer, position, sig_img_bytes, hw, svc, term_label, install):
    """Generate a signed receipt PDF."""
    from fpdf import FPDF
    def _s(t): return str(t or "").encode("latin-1",errors="replace").decode("latin-1")
    p = FPDF(); p.add_page(); p.set_auto_page_break(True, margin=15)
    # Header
    p.set_fill_color(31,20,80); p.rect(0,0,210,30,"F")
    p.set_fill_color(0,181,163); p.rect(0,30,210,2,"F")
    p.set_text_color(255,255,255); p.set_font("Helvetica","B",16)
    p.set_y(8); p.cell(0,8,"SY COMMS LTD - Signed Agreement Receipt",ln=True,align="C")
    p.set_font("Helvetica","",8); p.set_text_color(0,181,163)
    p.cell(0,6,"hello@sycomms.co.uk  |  01743 667419  |  www.sycomms.co.uk",ln=True,align="C")
    p.set_text_color(0,0,0); p.set_y(38)
    # Deal summary
    p.set_font("Helvetica","B",10); p.set_fill_color(245,247,255)
    p.cell(0,7,_s(f"  Agreement Summary - {comp}"),fill=True,ln=True)
    p.set_font("Helvetica","",9)
    rows = [("Company",_s(comp)),("Signed by",_s(f"{signer} ({position})")),
            ("Date",date.today().strftime("%d %B %Y")),
            ("Monthly Lease",f"GBP {hw:.2f}/mo"),
            ("Monthly Services",f"GBP {svc:.2f}/mo"),
            ("Total Monthly",f"GBP {hw+svc:.2f}/mo (excl. VAT)"),
            ("Agreement Term",_s(term_label)),("Installation",_s(install))]
    for i,(lbl,val) in enumerate(rows):
        p.set_fill_color(248,249,255) if i%2==0 else p.set_fill_color(255,255,255)
        p.cell(60,6,_s(f"  {lbl}:"),fill=True,ln=False)
        p.cell(0,6,_s(str(val)),fill=True,ln=True)
    p.ln(6)
    # Signature
    p.set_font("Helvetica","B",10); p.set_fill_color(245,247,255)
    p.cell(0,7,"  Customer Signature",fill=True,ln=True)
    p.ln(2)
    if sig_img_bytes:
        try:
            import tempfile,os
            with tempfile.NamedTemporaryFile(suffix=".png",delete=False) as tf:
                tf.write(sig_img_bytes); tp=tf.name
            p.image(tp,x=p.l_margin,y=p.get_y(),w=80,h=22)
            os.unlink(tp); p.ln(24)
        except Exception: p.ln(6)
    p.set_font("Helvetica","",9)
    p.cell(0,5,_s(f"Signed: {signer}"),ln=True)
    p.cell(0,5,_s(f"Position: {position}"),ln=True)
    p.cell(0,5,_s(f"Date: {date.today().strftime('%d %B %Y')}"),ln=True)
    p.ln(6)
    p.set_font("Helvetica","I",7); p.set_text_color(130,130,130)
    p.multi_cell(0,4,"By submitting this form, the signatory confirms agreement to the SY Comms "
                 "proposal and Terms & Conditions: https://sycomms.co.uk/terms-conditions",align="C")
    p.set_text_color(0,0,0)
    return bytes(p.output())

def _email_receipt(pdf_bytes, comp, signer, signed_date):
    """Email the signed receipt to SY Comms sales team."""
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.base import MIMEBase
    from email.mime.text import MIMEText
    from email import encoders
    secrets = st.secrets if hasattr(st,"secrets") else {}
    host  = secrets.get("SMTP_HOST","smtp.office365.com")
    port  = int(secrets.get("SMTP_PORT",587))
    user  = secrets.get("SMTP_USER","sales@sycomms.co.uk")
    pwd   = secrets.get("SMTP_PASS","")
    notify = secrets.get("NOTIFY_EMAIL","sales@sycomms.co.uk")
    if not pwd:
        return False,"SMTP password not configured in portal secrets."
    msg = MIMEMultipart()
    msg["From"]    = f"SY Comms Portal <{user}>"
    msg["To"]      = notify
    msg["Subject"] = f"✅ Signed Agreement — {comp} ({signed_date})"
    body = ("A customer has signed their agreement via the remote portal.\n\n"
            f"Company: {comp}\nSigned by: {signer}\nDate: {signed_date}\n\n"
            "Please find the signed receipt attached.")
    msg.attach(MIMEText(body, "plain"))
    att = MIMEBase("application","pdf")
    att.set_payload(pdf_bytes)
    encoders.encode_base64(att)
    att.add_header("Content-Disposition","attachment",
                   filename=f"Signed_Receipt_{comp.replace(' ','_')}.pdf")
    msg.attach(att)
    try:
        with smtplib.SMTP(host,port) as srv:
            srv.ehlo(); srv.starttls(); srv.ehlo()
            srv.login(user,pwd)
            srv.sendmail(user,notify,msg.as_string())
        return True,"Sent"
    except Exception as e:
        return False,str(e)

if st.button("📨 Submit Signed Agreement", use_container_width=True,
             type="primary", disabled=not _ready, key="rs_submit"):
    signed_date = date.today().strftime("%d %B %Y")
    # Build receipt PDF
    receipt_pdf = _build_receipt_pdf(
        comp=comp_name, signer=sig_name_rs, position=sig_pos_rs,
        sig_img_bytes=sig_bytes_rs,
        hw=hw_rental, svc=svc_total, term_label=lease_label, install=install_type
    )
    # Email to SY Comms
    _email_ok, _email_msg = _email_receipt(receipt_pdf, comp_name, sig_name_rs, signed_date)
    st.session_state["_rs_receipt_pdf"]  = receipt_pdf
    st.session_state["_rs_receipt_name"] = f"SYComms_Signed_{comp_name.replace(' ','_')}_{signed_date.replace(' ','_')}.pdf"
    st.session_state["_rs_submitted"]    = True
    st.session_state["_rs_email_ok"]     = _email_ok
    st.session_state["_rs_signer"]       = sig_name_rs
    st.rerun()

if st.session_state.get("_rs_submitted"):
    signer_display = st.session_state.get("_rs_signer","")
    st.balloons()
    st.success(f"🎉 Thank you, {signer_display}! Your agreement has been submitted.")
    st.markdown(f"""
    <div class="sy-card" style="border-left-color:#1a7a40">
      <strong>Reference:</strong> {comp_name} — signed {date.today().strftime('%d %B %Y')}<br>
      <strong>Signed by:</strong> {signer_display}<br>
      <strong>Your SY Comms consultant will be in touch shortly.</strong>
    </div>""", unsafe_allow_html=True)
    _receipt = st.session_state.get("_rs_receipt_pdf")
    _rname   = st.session_state.get("_rs_receipt_name","signed_receipt.pdf")
    if _receipt:
        st.download_button("📄 Download Your Signed Copy",data=_receipt,
                           file_name=_rname,mime="application/pdf",
                           use_container_width=True,key="rs_dl_receipt")
    if st.session_state.get("_rs_email_ok"):
        st.caption("✅ A copy has been sent to the SY Comms team.")
    else:
        st.caption("📋 Your agreement has been recorded. The SY Comms team will follow up shortly.")
    st.markdown("📞 **Questions?** Call us on 01743 667419 or email sales@sycomms.co.uk")

# ── Footer ────────────────────────────────────────────────────────────────────
st.markdown(f"""
<div class="sy-footer">
  SY Comms Ltd &nbsp;·&nbsp; Suite C Jupiter House, Shrewsbury Business Park, SY2 6LG<br>
  Registered in England No. 15722588 &nbsp;·&nbsp; VAT No. 467 8165 48<br>
  www.sycomms.co.uk
</div>
""", unsafe_allow_html=True)
