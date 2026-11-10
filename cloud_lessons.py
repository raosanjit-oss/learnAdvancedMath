"""Optional Supabase accounts and storage; local mode needs no cloud account."""

from datetime import datetime, timezone
from uuid import UUID

import streamlit as st
from app_settings import get_setting


def setting(name, default=None):
    """Compatibility wrapper kept to make this beginner-facing file readable."""
    return get_setting(name, default)


def enabled():
    return str(setting("PUBLIC_DEPLOYMENT", "false")).lower() == "true"


def auth_options():
    """Tell Supabase where account-confirmation emails should return."""
    app_url = str(setting("APP_URL", "")).strip().rstrip("/")
    if not app_url:
        return {}
    return {"email_redirect_to": app_url}


def confirmation_details(email, code):
    """Build the Supabase request for a six-digit email confirmation code."""
    return {"email": email.strip(), "token": code.strip(), "type": "email"}


def client():
    # Never cache this across users: its auth session belongs to one browser.
    if "supabase_client" not in st.session_state:
        from supabase import create_client
        url = setting("SUPABASE_URL")
        key = setting("SUPABASE_PUBLISHABLE_KEY")
        if not url or not key:
            raise ValueError("Configure Supabase before enabling the public app.")
        st.session_state.supabase_client = create_client(url, key)
    return st.session_state.supabase_client


def require_login():
    try:
        db = client()
    except ValueError as error:
        st.error(str(error))
        st.stop()
    if db.auth.get_session():
        try:
            user = db.auth.get_user().user
            if user:
                allowed_emails = {email.strip().lower() for email in str(setting("BETA_EMAILS", "")).split(",") if email.strip()}
                if (user.email or "").lower() not in allowed_emails:
                    st.error("This account isn't on the beta invitation list yet.")
                    if st.button("Use another account"):
                        db.auth.sign_out()
                        st.session_state.clear()
                        st.rerun()
                    st.stop()
                st.session_state.cloud_user_id = user.id
                with st.sidebar:
                    if st.button("Sign out"):
                        db.auth.sign_out()
                        st.session_state.clear()
                        st.rerun()
                return
        except Exception:
            st.session_state.pop("supabase_client", None)
            st.session_state.pop("cloud_user_id", None)
            st.error("Your session expired. Reload the page and sign in again.")
            st.stop()
    st.title("Your space to understand.")
    st.caption("Sign in or create an invited beta account. Your lessons stay private.")
    sign_in_tab, create_tab = st.tabs(["Sign in", "Create account"])
    with sign_in_tab, st.form("sign_in", clear_on_submit=True):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Sign in")
    if submitted:
        try:
            db.auth.sign_in_with_password({"email": email, "password": password})
            st.rerun()
        except Exception:
            st.error("Could not sign in. Check your email and password.")
    with create_tab, st.form("create_account", clear_on_submit=True):
        new_email = st.text_input("Invited email", key="new_email")
        new_password = st.text_input("Create password", type="password", key="new_password")
        create = st.form_submit_button("Create account")
    if create:
        allowed_emails = {email.strip().lower() for email in str(setting("BETA_EMAILS", "")).split(",") if email.strip()}
        if new_email.strip().lower() not in allowed_emails:
            st.error("That email isn't on the beta invitation list.")
        elif len(new_password) < 8:
            st.error("Use a password with at least 8 characters.")
        else:
            try:
                sign_up_details = {"email": new_email.strip(), "password": new_password}
                options = auth_options()
                if options:
                    sign_up_details["options"] = options
                response = db.auth.sign_up(sign_up_details)
                if response.session:
                    st.rerun()
                else:
                    st.success("Check your email to confirm your account, then return here to sign in.")
            except Exception:
                st.error("Could not create that account. It may already exist.")
    with create_tab:
        st.divider()
        st.caption("Confirm with the six-digit code from your email")
        with st.form("confirm_account", clear_on_submit=True):
            confirmation_email = st.text_input("Account email", key="confirmation_email")
            confirmation_code = st.text_input("Confirmation code", max_chars=6, key="confirmation_code")
            confirm = st.form_submit_button("Confirm account")
    if confirm:
        if not confirmation_code.strip().isdigit() or len(confirmation_code.strip()) != 6:
            st.error("Enter the six-digit code from your newest email.")
        else:
            try:
                db.auth.verify_otp(confirmation_details(confirmation_email, confirmation_code))
                st.rerun()
            except Exception:
                st.error("That code is invalid or expired. Request a new one below.")
    with create_tab:
        st.caption("Need a new code?")
        with st.form("resend_confirmation", clear_on_submit=True):
            resend_email = st.text_input("Account email", key="resend_email")
            resend = st.form_submit_button("Send a new confirmation email")
    if resend:
        allowed_emails = {email.strip().lower() for email in str(setting("BETA_EMAILS", "")).split(",") if email.strip()}
        if resend_email.strip().lower() not in allowed_emails:
            st.error("That email isn't on the beta invitation list.")
        else:
            try:
                resend_details = {"type": "signup", "email": resend_email.strip()}
                options = auth_options()
                if options:
                    resend_details["options"] = options
                db.auth.resend(resend_details)
                st.success("A new confirmation email is on its way. Use only its newest six-digit code.")
            except Exception:
                st.error("Could not resend yet. Wait one minute, then try again.")
    st.caption("This first beta is invite-only.")
    st.stop()


def check_allowance():
    db = client()
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    attempts = db.table("lessons").select("id").gte("created_at", today).execute().data
    if len(attempts) >= 2:
        raise ValueError("You've reached the beta limit of two new lessons per day. Try tomorrow.")


def reserve_lesson(directory, topic):
    check_allowance()
    db = client()
    db.table("lessons").insert({
        "id": str(UUID(directory.name)), "user_id": st.session_state.cloud_user_id,
        "topic": topic, "status": "saved",
    }).execute()


def upload_video(directory, duration):
    db = client()
    lesson_id = str(UUID(directory.name))
    video = directory / "lesson.mp4"
    if video.stat().st_size > 50 * 1024 * 1024:
        raise ValueError("This video exceeds the beta's 50 MB storage limit.")
    path = f"{st.session_state.cloud_user_id}/{lesson_id}/lesson.mp4"
    bucket = db.storage.from_("lesson-videos")
    # Upload once. A retry may find that the upload succeeded before metadata did.
    try:
        with video.open("rb") as file:
            bucket.upload(path, file, file_options={"content-type": "video/mp4", "upsert": "false"})
    except Exception as error:
        if "already exists" not in str(error).lower() and "duplicate" not in str(error).lower():
            raise
    db.table("lessons").update({"status": "complete", "duration": duration, "video_path": path}).eq("id", lesson_id).execute()
    return path


def recent_lessons():
    return client().table("lessons").select("id,topic,duration,video_path").eq("status", "complete").order("created_at", desc=True).limit(12).execute().data


def video_url(path):
    # RLS checks ownership before issuing a link that lasts one hour.
    return client().storage.from_("lesson-videos").create_signed_url(path, 3600)["signedURL"]
