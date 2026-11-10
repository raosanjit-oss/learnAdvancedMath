"""Small shared helper for local .env values and Streamlit Cloud secrets."""

import os


def get_setting(name, default=None):
    value = os.getenv(name)
    if value is not None:
        return value
    try:
        import streamlit as st
        return st.secrets.get(name, default)
    except (FileNotFoundError, RuntimeError):
        return default
