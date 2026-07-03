# ─────────────────────────────────────────────────────────────────────────────
# ADD THIS AS A NEW TAB in your existing app.py
# 1. Add "📨 Remote Signing" to the st.tabs() list
# 2. Paste this block as the new tab's content
# 3. Add GITHUB_TOKEN to your Streamlit Cloud secrets
# ─────────────────────────────────────────────────────────────────────────────

# In your st.tabs() line, add the new tab:
# tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
#   "📄 Proposal Summary", "🖋️ Order Form Preview",
#   "📥 Download Documents", "👤 Customer View",
#   "✍️ Sign & Send", "📨 Remote Signing"
# ])

# ── REMOTE SIGNING TAB ────────────────────────────────────────────────────────
# with tab6:
import secrets as _secrets
import requests as _requests

GITHUB_TOKEN_RS   = st.secrets.get("GITHUB_TOKEN", "")
SIGNING_PORTAL_URL = st.secrets.get("SIGNING_PORTAL_URL",
    "https://YOUR-SIGNING-APP.streamlit.app")  # ← set this in secrets

def create_signing_session(docs, customer_name, customer_email, sender_email, message):
    """Upload documents to a GitHub Gist and return (gist_id, signing_url)."""
    token = _secrets.token_urlsafe(12)
    session_data = {
        "token": token,
        "customer_name": customer_name,
        "customer_email": customer_email,
        "sender_email": sender_email,
        "message": message,
        "status": "pending",
        "created_at": date.today().isoformat(),
    }
    files = {"session.json": {"content": json.dumps(session_data, indent=2)}}
    for i, (fname, pdf_bytes) in enumerate(docs, 1):
        b64 = base64.b64encode(pdf_bytes).decode()
        files[f"doc_{i}_{fname}.b64"] = {"content": b64}

    hdrs = {"Authorization": f"token {GITHUB_TOKEN_RS}",
            "Accept": "application/vnd.github+json"}
    resp = _requests.post(
        "https://api.github.com/gists",
        json={"files": files, "public": False,
              "description": f"Novalink Signing - {customer_name}"},
        headers=hdrs, timeout=30
    )
    if resp.status_code != 201:
        return None, f"GitHub error {resp.status_code}: {resp.text[:200]}"
    gist_id = resp.json()["id"]
    signing_url = f"{SIGNING_PORTAL_URL}?gist={gist_id}"
    return gist_id, signing_url


def send_signing_invite(to_email, customer_name, signing_url, message, em_cfg):
    """Email the customer their signing link."""
    try:
        msg            = MIMEMultipart()
        msg["From"]    = f"{em_cfg.get('from_name','Novalink Hardware')} <{em_cfg.get('username','')}>"
        msg["To"]      = to_email
        msg["Subject"] = f"Please sign your documents - Novalink Hardware"
        body = f"""<html><body style="font-family:Arial,sans-serif;color:#333;max-width:600px;margin:0 auto">
          <div style="background:#0d2e4a;padding:20px 30px;border-radius:8px 8px 0 0">
            <h2 style="color:#fff;margin:0"><span style="color:#00b4d8">Novalink</span> Hardware</h2></div>
          <div style="background:#f9f9f9;padding:24px 30px;border:1px solid #e0e8e8;border-top:none">
            <p>Dear {customer_name},</p>
            {"<p>" + message + "</p>" if message else ""}
            <p>Your documents are ready for your electronic signature. Please click the button below to review and sign:</p>
            <div style="text-align:center;margin:24px 0">
              <a href="{signing_url}" style="background:#0077a8;color:#fff;padding:14px 32px;
                border-radius:8px;text-decoration:none;font-weight:bold;font-size:1rem">
                ✍️ Review &amp; Sign Documents
              </a>
            </div>
            <p style="font-size:0.85rem;color:#888">Or copy this link into your browser:<br/>
              <a href="{signing_url}" style="color:#0077a8">{signing_url}</a></p>
            <p>Kind regards,<br/><strong>{em_cfg.get('from_name','Novalink Hardware')}</strong></p>
          </div></body></html>"""
        msg.attach(MIMEText(body, "html"))
        with smtplib.SMTP(em_cfg.get("smtp_host","smtp.gmail.com"),
                          int(em_cfg.get("smtp_port", 587))) as srv:
            srv.ehlo(); srv.starttls(); srv.ehlo()
            srv.login(em_cfg["username"], em_cfg["password"])
            srv.sendmail(em_cfg["username"], [to_email], msg.as_string())
        return True, "Invite sent"
    except Exception as e:
        return False, str(e)


# ── TAB UI ────────────────────────────────────────────────────────────────────
st.markdown("### 📨 Send Documents for Remote Signing")
st.caption("Upload one or more PDFs and send the customer a secure signing link — no need for them to be present.")

if not GITHUB_TOKEN_RS:
    st.warning("GitHub token not configured. Add `GITHUB_TOKEN` to your Streamlit Cloud secrets.")
    st.info("👉 Create one at github.com → Settings → Developer settings → Personal access tokens → New token (select 'gist' scope)")
    st.stop()

rs_col1, rs_col2 = st.columns([3, 2])

with rs_col1:
    st.markdown("**📎 Upload Documents**")
    uploaded_docs = st.file_uploader(
        "Upload PDFs to send for signing",
        type=["pdf"], accept_multiple_files=True,
        key="rs_docs", label_visibility="collapsed"
    )
    if uploaded_docs:
        for uf in uploaded_docs:
            st.markdown(f"- 📄 {uf.name} ({len(uf.getvalue())//1024} KB)")

with rs_col2:
    st.markdown("**👤 Customer Details**")
    rs_name    = st.text_input("Customer name", value=comp_name or "", key="rs_name")
    rs_email   = st.text_input("Customer email", value=director_email or billing_email or "", key="rs_email")
    rs_cc      = st.text_input("CC (your email)", value=em_cfg.get("reply_to", em_cfg.get("username","")), key="rs_cc")
    rs_message = st.text_area("Personal message (optional)", height=80, key="rs_msg",
                              placeholder="e.g. Please review and sign at your earliest convenience.")

st.markdown("")
rs_ready = bool(uploaded_docs and rs_name and rs_email)

if not rs_ready:
    if not uploaded_docs: st.caption("Upload at least one PDF to continue.")
    if not rs_name:       st.caption("Enter the customer name.")
    if not rs_email:      st.caption("Enter the customer email.")

if st.button("📨 Create Signing Session & Email Customer",
             type="primary", use_container_width=True, disabled=not rs_ready):
    with st.spinner("Uploading documents and creating signing link..."):
        docs_list = [(uf.name, uf.getvalue()) for uf in uploaded_docs]
        gist_id, result = create_signing_session(
            docs_list, rs_name, rs_email, rs_cc, rs_message
        )
    if gist_id:
        signing_url = result
        st.success(f"✅ Signing session created!")
        st.markdown(f"**Signing link:**")
        st.code(signing_url)

        # Send invite email
        with st.spinner("Sending invite email..."):
            em_cfg_rs = st.session_state.active_config.get("email", {})
            ok, msg   = send_signing_invite(rs_email, rs_name, signing_url, rs_message, em_cfg_rs)
        if ok:
            st.success(f"📧 Invite email sent to {rs_email}")
        else:
            st.error(f"Email failed: {msg}")
            st.info(f"You can manually share this link with the customer: {signing_url}")

        st.markdown(f"""
        <div style="background:#e8f4fb;border-left:4px solid #00b4d8;border-radius:0 8px 8px 0;
                    padding:0.8rem 1rem;margin-top:0.5rem;font-size:0.85rem;color:#0a3d62">
          📋 <strong>Session reference:</strong> {gist_id[:12].upper()}<br/>
          👤 <strong>Customer:</strong> {rs_name} ({rs_email})<br/>
          📄 <strong>Documents:</strong> {len(docs_list)}<br/>
          The signing link is valid until the customer signs. Once signed, all parties receive the completed documents by email.
        </div>""", unsafe_allow_html=True)
    else:
        st.error(f"Could not create signing session: {result}")
