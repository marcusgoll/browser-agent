#!/usr/bin/env python3
"""Tests for X.com Google OAuth login probe helpers."""
import importlib.util
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "x_google_oauth_login.py"
spec = importlib.util.spec_from_file_location("x_google_oauth_login", MODULE_PATH)
xlogin = importlib.util.module_from_spec(spec)
spec.loader.exec_module(xlogin)


def test_sanitize_url_redacts_query_and_fragment():
    assert xlogin.sanitize_url("https://accounts.google.com/v3/signin/identifier?client_id=abc#frag") == (
        "https://accounts.google.com/v3/signin/identifier?[redacted]"
    )
    assert xlogin.sanitize_url("https://x.com/home") == "https://x.com/home"


def test_build_launch_args_hides_automation_and_uses_realistic_user_agent():
    args = xlogin.build_launch_args("Mozilla/5.0 TestChrome")

    assert "--disable-blink-features=AutomationControlled" in args
    assert "--disable-features=IsolateOrigins,site-per-process" in args
    assert "--no-sandbox" in args
    assert "--enable-automation" not in args
    assert "--headless" not in " ".join(args).lower()
    assert "--user-agent=Mozilla/5.0 TestChrome" in args


def test_stealth_init_script_masks_webdriver_and_supplies_chrome_runtime():
    script = xlogin.stealth_init_script()

    assert "navigator" in script
    assert "webdriver" in script
    assert "undefined" in script
    assert "window.chrome" in script
    assert "runtime" in script
    assert "plugins" in script


def test_is_google_oauth_iframe_url_detects_accounts_gsi_button():
    assert xlogin.is_google_oauth_iframe_url(
        "https://accounts.google.com/gsi/button?client_id=abc.apps.googleusercontent.com"
    ) is True
    assert xlogin.is_google_oauth_iframe_url("https://x.com/i/flow/login") is False


def test_classify_login_state_detects_google_oauth_boundary():
    state = xlogin.classify_login_state(
        url="https://accounts.google.com/v3/signin/identifier?continue=https://x.com",
        title="Sign in - Google Accounts",
        visible_text="Sign in with Google Use your Google Account",
    )

    assert state["status"] == "google_oauth_boundary"
    assert state["requires_user"] is True
    assert "Marcus" in state["next_action"]


def test_classify_login_state_detects_x_google_option_screen():
    state = xlogin.classify_login_state(
        url="https://x.com/i/jf/onboarding/web?mode=login",
        title="X - The Everything App / X",
        visible_text="See what's happening Select an option below Continue with Google Continue with Apple",
    )

    assert state["status"] == "x_login_google_option"
    assert state["requires_user"] is False


def test_classify_login_state_detects_x_login_screen_without_google_option():
    state = xlogin.classify_login_state(
        url="https://x.com/i/jf/onboarding/web?mode=login",
        title="X - The Everything App / X",
        visible_text="See what's happening Select an option below Continue with phone Continue with Apple Email or username",
    )

    assert state["status"] == "x_login_no_google_option"
    assert state["requires_user"] is True


def test_classify_login_state_detects_x_single_sign_on_callback_block():
    state = xlogin.classify_login_state(
        url="https://x.com/i/flow/single_sign_on",
        title="X",
        visible_text="Oops, something went wrong. Please try again later.",
    )

    assert state["status"] == "x_single_sign_on_blocked"
    assert state["requires_user"] is True


def test_classify_login_state_detects_logged_in_home():
    state = xlogin.classify_login_state(
        url="https://x.com/home",
        title="Home / X",
        visible_text="Home For you Following What is happening?!",
    )

    assert state["status"] == "logged_in"
    assert state["requires_user"] is False


def test_classify_login_state_detects_google_insecure_browser_error():
    state = xlogin.classify_login_state(
        url="https://accounts.google.com/signin",
        title="Sign in - Google Accounts",
        visible_text="Couldn't sign you in This browser or app may not be secure",
    )

    assert state["status"] == "google_insecure_browser_blocked"
    assert state["requires_user"] is True
