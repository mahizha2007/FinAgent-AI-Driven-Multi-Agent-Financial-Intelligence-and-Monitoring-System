from __future__ import annotations

from datetime import timedelta

import streamlit as st

from utils.timezone import now_ist, now_ist_iso, to_ist_timestamp


SESSION_TIMEOUT_MINUTES = 30


def require_login(database_manager, app_name: str) -> str:
    """Render a login/register gate and return the authenticated username."""
    session_key = f"{app_name}_authenticated_user"
    last_activity_key = f"{app_name}_last_activity"
    auth_message_key = f"{app_name}_auth_message"
    if st.session_state.get(session_key):
        last_activity = to_ist_timestamp(st.session_state.get(last_activity_key))
        if last_activity and now_ist() - last_activity > timedelta(minutes=SESSION_TIMEOUT_MINUTES):
            st.session_state.pop(session_key, None)
            st.session_state.pop(last_activity_key, None)
            st.session_state[auth_message_key] = "Your session expired after inactivity. Please sign in again."
        else:
            st.session_state[last_activity_key] = now_ist_iso()
            return st.session_state[session_key]

    if st.session_state.get(auth_message_key):
        st.warning(st.session_state.pop(auth_message_key))

    st.markdown(
        """
        <div class="hero-card">
            <div class="hero-title">Secure Access</div>
            <div class="hero-subtitle">
                Sign in with your approved username and password to use the financial assistant.
                New self-service accounts wait for admin approval before first login.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    login_tab, register_tab = st.tabs(["Login", "Register"])
    with login_tab:
        with st.form(key=f"{app_name}_login_form", clear_on_submit=False):
            username = st.text_input("Username", key=f"{app_name}_login_username")
            password = st.text_input("Password", type="password", key=f"{app_name}_login_password")
            submitted = st.form_submit_button("Login")
        if submitted:
            success, message = database_manager.authenticate_user_with_status(username, password)
            if success:
                st.session_state[session_key] = username.strip()
                st.session_state[last_activity_key] = now_ist_iso()
                st.success("Login successful.")
                st.rerun()
            else:
                st.error(message)

    with register_tab:
        with st.form(key=f"{app_name}_register_form", clear_on_submit=False):
            new_username = st.text_input("New Username", key=f"{app_name}_register_username")
            new_password = st.text_input("New Password", type="password", key=f"{app_name}_register_password")
            confirm_password = st.text_input("Confirm Password", type="password", key=f"{app_name}_register_confirm_password")
            register_submitted = st.form_submit_button("Create Account")
        st.caption("Password policy: at least 8 characters with uppercase, lowercase, number, and special character.")
        if register_submitted:
            if new_password != confirm_password:
                st.error("Passwords do not match.")
            else:
                success, message = database_manager.create_user(new_username, new_password, require_approval=True)
                if success:
                    st.success(message)
                else:
                    st.error(message)

    st.stop()


def logout_user(app_name: str) -> None:
    """Clear the authenticated session for the given app."""
    session_key = f"{app_name}_authenticated_user"
    st.session_state.pop(session_key, None)
    st.session_state.pop(f"{app_name}_last_activity", None)
