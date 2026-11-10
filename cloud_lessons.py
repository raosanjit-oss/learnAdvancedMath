"""Optional Supabase accounts and storage; local mode needs no cloud account."""

from datetime import datetime, timezone
import os
from uuid import UUID

import streamlit as st


def enabled():
    return os.getenv("PUBLIC_DEPLOYMENT", "false").lower() == "true"


def client():
    # Never cache this across users: its auth session belongs to one browser.
    if "supabase_client" not in st.session_state:
        from supabase import create_client
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_PUBLISHABLE_KEY")
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
                allowed_emails = {email.strip().lower() for email in os.getenv("BETA_EMAILS", "").split(",") if email.strip()}
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
    st.caption("Sign in to create videos and keep your lessons private.")
    with st.form("sign_in", clear_on_submit=True):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Sign in")
    if submitted:
        try:
            db.auth.sign_in_with_password({"email": email, "password": password})
            st.rerun()
        except Exception:
            st.error("Could not sign in. Check your email and password.")
    st.caption("This first beta is invite-only. Ask the app owner for an account.")
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
    # If an earlier upload succeeded but the metadata update failed, reuse it.
    try:
        bucket.create_signed_url(path, 60)
    except Exception:
        with video.open("rb") as file:
            bucket.upload(path, file, file_options={"content-type": "video/mp4"})
    db.table("lessons").update({"status": "complete", "duration": duration, "video_path": path}).eq("id", lesson_id).execute()
    return path


def recent_lessons():
    return client().table("lessons").select("id,topic,duration,video_path").eq("status", "complete").order("created_at", desc=True).limit(12).execute().data


def video_url(path):
    # RLS checks ownership before issuing a link that lasts one hour.
    return client().storage.from_("lesson-videos").create_signed_url(path, 3600)["signedURL"]
