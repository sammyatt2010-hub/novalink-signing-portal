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
params  = st.query_params
gist_id = params.get("gist", "")

# Try to capture client IP via Streamlit internals
_client_ip = "Not captured"
try:
    from streamlit.runtime.scriptrunner import get_script_run_ctx as _get_ctx
    from streamlit.runtime import get_instance as _get_rt
    _ctx = _get_ctx()
    if _ctx:
        _client_ip = _get_rt().get_client(_ctx.session_id).request.remote_ip or "Not captured"
except Exception:
    pass

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
    _session = None
    for fname in ("session.json",):
        if fname in files:
            raw = files[fname]
            if raw.get("truncated"):
                r2 = requests.get(raw["raw_url"], headers=hdrs, timeout=15)
                _session = json.loads(r2.text)
            else:
                _session = json.loads(raw["content"])
    if _session is not None:
        doc_bytes_list = []
        for fname in sorted(files.keys()):
            if fname.startswith("doc_") and fname.endswith(".b64"):
                raw = files[fname]
                if raw.get("truncated"):
                    r2 = requests.get(raw["raw_url"], headers=hdrs, timeout=30)
                    doc_bytes_list.append(base64.b64decode(r2.text))
                else:
                    doc_bytes_list.append(base64.b64decode(raw["content"]))
        return _session, doc_bytes_list, None
    # Fallback: any JSON file
    for fname, fdata in files.items():
        if fname.endswith(".json"):
            session = json.loads(fdata["content"])
            break
    else:
        return None, None, "No deal data found in this link."
    # Read original PDF docs (doc_*.b64)
    doc_bytes_list = []
    for fname in sorted(files.keys()):
        if fname.startswith("doc_") and fname.endswith(".b64"):
            raw = files[fname]
            if raw.get("truncated"):
                r2 = requests.get(raw["raw_url"], headers=hdrs, timeout=30)
                doc_bytes_list.append(base64.b64decode(r2.text))
            else:
                doc_bytes_list.append(base64.b64decode(raw["content"]))
    return session, doc_bytes_list, None

# Read token outside the cached function
_gh_token = ""
if hasattr(st, "secrets"):
    try:
        _gh_token = st.secrets.get("GITHUB_TOKEN", "")
    except Exception:
        pass

with st.spinner("Loading your proposal…"):
    deal, _orig_docs, _err = load_gist(gist_id, token=_gh_token)

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
col1, col2 = st.columns(2)
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
    f"By signing below, I/we confirm I have read and agree to the proposal and "
    f"SY Comms Terms & Conditions (https://sycomms.co.uk/terms-conditions). "
    f"Agreement term: {lease_label}."
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

def _build_receipt_pdf(comp, signer, position, sig_img_bytes, hw, svc, term_label, install, email="", ref_id="", ts="", ip_addr=""):
    """Generate a Certificate of Completion matching the main SY Comms app style."""
    from fpdf import FPDF
    import uuid as _uuid, hashlib as _hl, tempfile as _tf, os as _os
    from datetime import datetime as _dt
    def _s(t): return str(t or "").encode("latin-1",errors="replace").decode("latin-1")

    _envelope_id = ref_id.upper() or str(_uuid.uuid4()).upper()
    _doc_hash    = _hl.sha256(sig_img_bytes).hexdigest().upper() if sig_img_bytes else "N/A"
    _signed_at   = ts or _dt.now().strftime("%Y-%m-%d %H:%M UTC")
    _ip          = ip_addr or "Remote Signing Portal"
    _sig_method  = "Hand-drawn (Remote Signing Portal)"

    p = FPDF(); p.add_page(); p.set_auto_page_break(True, margin=15)

    # ── Header ────────────────────────────────────────────────────────────────
    p.set_fill_color(31,20,80); p.rect(0,0,210,22,"F")
    p.set_font("Helvetica","B",13); p.set_text_color(255,255,255)
    p.set_y(5); p.cell(0,6,"CERTIFICATE OF COMPLETION",ln=True,align="C")
    p.set_font("Helvetica","",8)
    p.cell(0,5,"SY Comms  |  Electronic Signing Record",ln=True,align="C")
    p.set_fill_color(0,181,163); p.rect(0,22,210,1.5,"F")
    p.set_text_color(0,0,0); p.ln(8)

    lx = p.l_margin

    def _section_hdr(title):
        p.set_font("Helvetica","B",9); p.set_fill_color(220,235,245); p.set_text_color(13,46,74)
        p.cell(0,6,_s(f"  {title}"),fill=True,ln=True); p.set_text_color(0,0,0)

    def _env_row(l,v,color=(0,0,0)):
        p.set_font("Helvetica","B",8); p.set_text_color(100,100,100)
        p.cell(52,5.5,_s(l),ln=False)
        p.set_font("Helvetica","",8); p.set_text_color(*color)
        p.cell(0,5.5,_s(str(v))[:70],ln=True); p.set_text_color(0,0,0)

    def _row3(c1,c2,c3,h=5.5,bold1=False):
        p.set_font("Helvetica","B" if bold1 else "",8)
        p.cell(65,h,_s(c1),border="B",ln=False)
        p.set_font("Helvetica","",8)
        p.cell(65,h,_s(c2),border="B",ln=False)
        p.cell(0, h,_s(c3),border="B",ln=True)

    # ── Envelope Summary ─────────────────────────────────────────────────────
    p.set_font("Helvetica","B",9); p.set_text_color(13,46,74)
    p.cell(0,6,"Envelope Summary",ln=True)
    p.set_draw_color(0,181,163); p.set_line_width(0.4)
    p.line(lx,p.get_y(),195,p.get_y()); p.set_line_width(0.2); p.set_draw_color(200,200,200)
    p.ln(2)
    _env_row("Envelope ID:", _envelope_id)
    _env_row("Status:", "COMPLETED", color=(0,140,70))
    _env_row("Subject:", f"SY Comms Proposal - {comp[:40]}")
    _env_row("Originator:", "SY Comms")
    _env_row("Signed Via:", "SY Comms Remote Signing Portal")
    _env_row("Time Zone:", "(UTC+00:00) Dublin, Edinburgh, Lisbon, London")
    _env_row("Originator Email:", "sales@sycomms.co.uk")
    p.ln(4)

    # ── Record Tracking ───────────────────────────────────────────────────────
    _section_hdr("Record Tracking")
    p.ln(1)
    _row3("Status","Holder","Location",bold1=True)
    _row3("Original","SY Comms","SY Comms Quotation Tool")
    _row3(_signed_at,"sales@sycomms.co.uk","Streamlit Cloud")
    p.ln(4)

    # ── Signer Events ─────────────────────────────────────────────────────────
    _section_hdr("Signer Events")
    p.ln(1); _row3("Signer Details","Signature","Timestamps",bold1=True)

    y_row = p.get_y()
    # Left column: signer info (stacked clearly)
    p.set_font("Helvetica","B",8); p.set_xy(lx, y_row)
    p.cell(65,5,_s(signer),ln=True)
    p.set_font("Helvetica","",8); p.set_x(lx)
    p.cell(65,5,_s(email or "-"),ln=True)
    p.set_x(lx); p.cell(65,5,_s(comp),ln=True)
    p.set_x(lx); p.cell(65,5,_s(f"Position: {position}"),ln=True)
    p.set_x(lx); p.set_font("Helvetica","I",7); p.set_text_color(80,80,80)
    p.cell(65,5,"Security: Remote Digital Signature",ln=True)
    p.set_x(lx); p.cell(65,5,_s(f"IP Address: {_ip}"),ln=True)
    p.set_x(lx); p.cell(65,5,_s(f"Method: {_sig_method}"),ln=True)
    p.set_text_color(0,0,0)
    # Middle column: signature image
    if sig_img_bytes:
        try:
            with _tf.NamedTemporaryFile(suffix=".png",delete=False) as _stf:
                _stf.write(sig_img_bytes); _sp=_stf.name
            p.image(_sp,x=lx+67,y=y_row,w=60,h=18)
            _os.unlink(_sp)
        except Exception: pass
    # Right column: timestamps
    p.set_xy(lx+135,y_row); p.set_font("Helvetica","",7.5)
    p.cell(0,5,_s(f"Sent:   {_signed_at}"),ln=True)
    p.set_xy(lx+135,y_row+5); p.cell(0,5,_s(f"Viewed: {_signed_at}"),ln=True)
    p.set_xy(lx+135,y_row+10); p.cell(0,5,_s(f"Signed: {_signed_at}"),ln=True)
    p.set_y(max(p.get_y(), y_row+38))
    p.ln(2); p.set_draw_color(200,200,200); p.line(lx,p.get_y(),195,p.get_y()); p.ln(4)

    # ── Document Fields ────────────────────────────────────────────────────────
    _section_hdr("Agreement Summary")
    p.ln(1)
    rows = [("Company",comp),("Signed by",f"{signer} ({position})"),
            ("Date Signed",date.today().strftime("%d %B %Y")),
            ("Monthly Lease",f"GBP {hw:.2f}/mo"),
            ("Monthly Services",f"GBP {svc:.2f}/mo"),
            ("Total Monthly",f"GBP {hw+svc:.2f}/mo (excl. VAT)"),
            ("Agreement Term",term_label),("Installation",install),
            ("Document Hash (SHA-256)",_doc_hash[:40]+"...")]
    for i,(lbl,val) in enumerate(rows):
        p.set_fill_color(248,249,255) if i%2==0 else p.set_fill_color(255,255,255)
        p.set_font("Helvetica","B",8); p.set_text_color(80,80,80)
        p.cell(60,5.5,_s(f"  {lbl}:"),fill=True,ln=False)
        p.set_font("Helvetica","",8); p.set_text_color(0,0,0)
        p.cell(0,5.5,_s(str(val)),fill=True,ln=True)
    p.ln(4)

    # ── Footer ─────────────────────────────────────────────────────────────────
    p.set_font("Helvetica","I",7); p.set_text_color(130,130,130)
    p.multi_cell(0,4,
        "This certificate confirms the electronic execution of the above agreement. "
        "The signatory confirms agreement to SY Comms Terms & Conditions: "
        "https://sycomms.co.uk/terms-conditions",align="C")
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
    from datetime import datetime as _dtnow
    _ts_now = _dtnow.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    st.session_state["_rs_ts"] = _ts_now
    receipt_pdf = _build_receipt_pdf(
        comp=comp_name, signer=sig_name_rs, position=sig_pos_rs,
        sig_img_bytes=sig_bytes_rs,
        hw=hw_rental, svc=svc_total, term_label=lease_label, install=install_type,
        email=deal.get("customer_email",""),
        ref_id=gist_id[:36],
        ts=_ts_now,
        ip_addr=_client_ip
    )
    # Email to SY Comms
    _email_ok, _email_msg = _email_receipt(receipt_pdf, comp_name, sig_name_rs, signed_date)
    st.session_state["_rs_receipt_pdf"]  = receipt_pdf
    st.session_state["_rs_orig_docs"]    = _orig_docs or []
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
    _receipt   = st.session_state.get("_rs_receipt_pdf")
    _orig_docs = st.session_state.get("_rs_orig_docs", [])
    _rname     = st.session_state.get("_rs_receipt_name","signed_receipt.pdf")
    # Build signed pack: stamp signature on relevant pages + append certificate
    if _receipt:
        try:
            from pypdf import PdfWriter, PdfReader
            import fpdf as _fpdf_mod

            _ts_stamp = st.session_state.get("_rs_ts", "")

            def _make_stamp_at(sig_bytes, signer, ts, y_mm):
                """Create A4 overlay with signature block at given y position (mm)."""
                def _ss(t): return str(t or "").encode("latin-1",errors="replace").decode("latin-1")
                sp = _fpdf_mod.FPDF(); sp.set_margins(0,0,0)
                sp.add_page(); sp.set_auto_page_break(False)
                if sig_bytes:
                    try:
                        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as _stf:
                            _stf.write(sig_bytes); _stmp = _stf.name
                        sp.image(_stmp, x=15, y=y_mm, w=55, h=13)
                        os.unlink(_stmp)
                    except Exception:
                        pass
                sp.set_xy(15, y_mm + 14)
                sp.set_font("Helvetica","",6.5); sp.set_text_color(60,60,60)
                sp.cell(0,3.5,_ss(f"Signed: {signer}  |  {ts}"),ln=True)
                return bytes(sp.output())

            def _find_signed_y(page):
                """Find y position (in mm) of the LOWEST 'Signed:' on a page."""
                PAGE_H_PT = float(page.mediabox.height)  # points, origin bottom-left
                _hits = []
                def _visit(text, cm, tm, fd, fs):
                    if text and "signed" in text.lower():
                        # tm[5] is y in points from bottom; convert to mm from top
                        y_pt = tm[5]
                        y_mm = (PAGE_H_PT - y_pt) / 2.8346
                        _hits.append(y_mm)
                try:
                    page.extract_text(visitor_text=_visit)
                except Exception:
                    pass
                # Return lowest instance (highest y_mm = furthest down the page)
                return max(_hits) - 2 if _hits else None  # 2mm above the text

            _SIG_MARKERS = ("signed:", "for ", "authorised signatory",
                            "i/we confirm", "i confirm", "customer signature")

            writer = PdfWriter()
            for _doc in _orig_docs:
                reader = PdfReader(io.BytesIO(_doc))
                for page in reader.pages:
                    try:
                        page_text = page.extract_text() or ""
                        needs_sig = any(m in page_text.lower() for m in _SIG_MARKERS)
                    except Exception:
                        needs_sig = False; page_text = ""
                    if needs_sig:
                        y_pos = _find_signed_y(page)
                        if y_pos is None or y_pos > 270:
                            y_pos = 255  # fallback: near bottom
                        stamp_bytes = _make_stamp_at(sig_bytes_rs, sig_name_rs, _ts_stamp, y_pos)
                        stamp_reader = PdfReader(io.BytesIO(stamp_bytes))
                        page.merge_page(stamp_reader.pages[0])
                    writer.add_page(page)

            # Append Certificate of Completion
            writer.append(PdfReader(io.BytesIO(_receipt)))
            _merged = io.BytesIO()
            writer.write(_merged)
            _pack_bytes = _merged.getvalue()
            _pack_name  = _rname.replace("signed_receipt", "SIGNED_PACK")
        except Exception as _me:
            _pack_bytes = _receipt
            _pack_name  = _rname
        st.download_button("📄 Download Signed Documents Pack",
                           data=_pack_bytes, file_name=_pack_name,
                           mime="application/pdf",
                           use_container_width=True, key="rs_dl_receipt")
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
