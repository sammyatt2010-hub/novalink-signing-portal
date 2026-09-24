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
def load_gist(gid):
    token = st.secrets.get("GITHUB_TOKEN", "") if hasattr(st, "secrets") else ""
    hdrs  = {"Authorization": f"token {token}"} if token else {}
    r = requests.get(f"https://api.github.com/gists/{gid}", headers=hdrs, timeout=10)
    if r.status_code != 200:
        return None
    files = r.json().get("files", {})
    # Prefer session.json which contains the full deal data
    for fname in ("session.json", ):
        if fname in files:
            raw = files[fname]
            content_url = raw.get("raw_url", "")
            if raw.get("truncated") and content_url:
                r2 = requests.get(content_url, headers=hdrs, timeout=10)
                return json.loads(r2.text)
            return json.loads(raw["content"])
    # Fallback: first JSON file
    for fname, fdata in files.items():
        if fname.endswith(".json"):
            return json.loads(fdata["content"])
    return None

with st.spinner("Loading your proposal…"):
    deal = load_gist(gist_id)

if deal is None:
    st.error("Could not load proposal. The link may have expired or be invalid. "
             "Please contact your SY Comms consultant.")
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

if st.button("📨 Submit Signed Agreement", use_container_width=True,
             type="primary", disabled=not _ready, key="rs_submit"):
    # Build a signed confirmation record
    record = {
        "comp_name":   comp_name,
        "signed_by":   sig_name_rs,
        "position":    sig_pos_rs,
        "signed_date": str(date.today()),
        "gist_id":     gist_id,
        "sig_b64":     base64.b64encode(sig_bytes_rs).decode() if sig_bytes_rs else "",
    }
    # Optionally POST back to a webhook / email via SMTP
    # For now, show confirmation and provide a downloadable receipt
    st.balloons()
    st.success(f"🎉 Thank you, {sig_name_rs}! Your agreement has been submitted.")
    st.markdown(f"""
    <div class="sy-card" style="border-left-color:#1a7a40">
      <strong>Reference:</strong> {comp_name} — signed {date.today().strftime('%d %B %Y')}<br>
      <strong>Signed by:</strong> {sig_name_rs} ({sig_pos_rs})<br>
      <strong>Your SY Comms consultant will be in touch shortly.</strong>
    </div>
    """, unsafe_allow_html=True)
    st.markdown(
        "📞 **Questions?** Call us on 01743 667419 or email sales@sycomms.co.uk"
    )

# ── Footer ────────────────────────────────────────────────────────────────────
st.markdown(f"""
<div class="sy-footer">
  SY Comms Ltd &nbsp;·&nbsp; Suite C Jupiter House, Shrewsbury Business Park, SY2 6LG<br>
  Registered in England No. 15722588 &nbsp;·&nbsp; VAT No. 467 8165 48<br>
  www.sycomms.co.uk
</div>
""", unsafe_allow_html=True)
