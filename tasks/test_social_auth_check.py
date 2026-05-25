#!/usr/bin/env python3
"""Tests for safe social auth-state classifiers."""
import importlib.util
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "social_auth_check.py"
spec = importlib.util.spec_from_file_location("social_auth_check", MODULE_PATH)
auth = importlib.util.module_from_spec(spec)
spec.loader.exec_module(auth)


def test_sanitize_url_redacts_query_and_fragment():
    assert auth.sanitize_url("https://x.com/home?abc=123#frag") == "https://x.com/home?[redacted]"
    assert auth.sanitize_url("https://www.linkedin.com/feed/") == "https://www.linkedin.com/feed/"


def test_build_launch_args_hides_basic_automation_flags():
    args = auth.build_launch_args("Mozilla/5.0 TestChrome")
    joined = " ".join(args).lower()
    assert "--disable-blink-features=AutomationControlled" in args
    assert "--enable-automation" not in args
    assert "--headless" not in joined
    assert "--user-agent=Mozilla/5.0 TestChrome" in args


def test_classify_x_authenticated_home():
    state = auth.classify_x_state("https://x.com/home", "Home / X", "Home For you Following")
    assert state["status"] == auth.AUTHENTICATED
    assert state["screenshot_required"] is False


def test_classify_x_authenticated_home_ignores_timeline_challenge_words():
    state = auth.classify_x_state(
        "https://x.com/home",
        "Home / X",
        "Home For you Following What's happening? Today's News Secret Service White House Checkpoint",
    )
    assert state["status"] == auth.AUTHENTICATED
    assert state["reason"] == "x_home_loaded"


def test_classify_x_login_required():
    state = auth.classify_x_state(
        "https://x.com/i/flow/login",
        "X",
        "Log in to X Phone, email, or username",
    )
    assert state["status"] == auth.LOGIN_REQUIRED
    assert state["screenshot_required"] is True


def test_classify_x_google_challenge_boundary():
    state = auth.classify_x_state(
        "https://accounts.google.com/v3/signin/identifier?client_id=secret",
        "Sign in - Google Accounts",
        "Use your Google Account",
    )
    assert state["status"] == auth.MFA_OR_CHALLENGE_REQUIRED
    assert state["reason"] == "google_oauth_or_account_challenge"


def test_classify_linkedin_authenticated_feed():
    state = auth.classify_linkedin_state(
        "https://www.linkedin.com/feed/",
        "Feed | LinkedIn",
        "Home My Network Jobs Messaging Notifications Start a post",
    )
    assert state["status"] == auth.AUTHENTICATED


def test_classify_linkedin_authenticated_feed_ignores_feed_challenge_words():
    state = auth.classify_linkedin_state(
        "https://www.linkedin.com/feed/",
        "Feed | LinkedIn",
        "Home My Network Jobs Messaging Notifications Start a post Security checklist post in feed",
    )
    assert state["status"] == auth.AUTHENTICATED


def test_classify_linkedin_login_required():
    state = auth.classify_linkedin_state(
        "https://www.linkedin.com/login",
        "LinkedIn Login",
        "Sign in Email or phone Password",
    )
    assert state["status"] == auth.LOGIN_REQUIRED


def test_classify_linkedin_feed_with_signin_as_not_authenticated():
    state = auth.classify_linkedin_state(
        "https://www.linkedin.com/feed/",
        "LinkedIn",
        "Discover new opportunities Sign in Join now Sign in as Marcus m*****@gmail.com",
    )
    assert state["status"] == auth.LOGIN_REQUIRED
    assert state["reason"] == "linkedin_login_screen"


def test_classify_linkedin_challenge():
    state = auth.classify_linkedin_state(
        "https://www.linkedin.com/checkpoint/challenge/",
        "Security Verification",
        "Verify your identity",
    )
    assert state["status"] == auth.MFA_OR_CHALLENGE_REQUIRED


def test_classify_reddit_authenticated():
    state = auth.classify_reddit_state(
        "https://www.reddit.com/",
        "Reddit - Dive into anything",
        "Home Popular Create Post Profile",
    )
    assert state["status"] == auth.AUTHENTICATED


def test_classify_reddit_authenticated_ignores_feed_challenge_words():
    state = auth.classify_reddit_state(
        "https://www.reddit.com/",
        "Reddit - Dive into anything",
        "Home Popular Create Post Profile security checkpoint discussion",
    )
    assert state["status"] == auth.AUTHENTICATED


def test_classify_reddit_login_required():
    state = auth.classify_reddit_state(
        "https://www.reddit.com/login/",
        "Log In - Reddit",
        "Log In Username Password Sign Up",
    )
    assert state["status"] == auth.LOGIN_REQUIRED


def test_all_platforms_return_required_status_vocabulary():
    allowed = {auth.AUTHENTICATED, auth.LOGIN_REQUIRED, auth.MFA_OR_CHALLENGE_REQUIRED, auth.UNKNOWN}
    for platform, cfg in auth.PLATFORMS.items():
        state = cfg["classifier"]("https://example.com", "", "")
        assert state["status"] in allowed, platform


def test_normalize_status_for_monitor_vocabulary():
    assert auth.normalize_status(auth.AUTHENTICATED) == "authenticated"
    assert auth.normalize_status(auth.MFA_OR_CHALLENGE_REQUIRED) == "requires_user"
    assert auth.normalize_status(auth.LOGIN_REQUIRED) == "expired"
    assert auth.normalize_status(auth.UNKNOWN) == "ambiguous"
    assert auth.normalize_status("new_error") == "infra_error"


def test_build_auth_result_includes_normalized_status_and_policy():
    state = auth._state(auth.LOGIN_REQUIRED, "x_login_screen", "refresh login", True)
    result = auth.build_auth_result(
        platform="x",
        profile="x-profile",
        state=state,
        url="https://x.com/i/flow/login?x=1",
        title="X Login",
        started_at=100,
        screenshot="/app/output/blocked.png",
        proof_path="/app/output/runs/run/proof.json",
    )
    assert result["normalized_status"] == "expired"
    assert result["secrets_policy"] == auth.SECRETS_POLICY
    assert result["url"] == "https://x.com/i/flow/login?[redacted]"
    assert result["proof_bundle"] == "/app/output/runs/run/proof.json"


def test_default_latest_output_path_is_platform_scoped():
    path = auth.default_latest_output_path("linkedin")
    assert str(path).endswith("social-auth-linkedin-latest.json")


def test_auth_result_omits_raw_body_text():
    state = auth._state(auth.UNKNOWN, "unknown", "manual review", True)
    result = auth.build_auth_result(
        platform="reddit",
        profile="reddit-profile",
        state=state,
        url="https://www.reddit.com/",
        title="Reddit",
        started_at=100,
    )
    assert "visible_text" not in result
    assert "body" not in result


def test_auth_result_references_proof_bundle_path():
    state = auth._state(auth.AUTHENTICATED, "x_home_loaded", "ready")
    result = auth.build_auth_result(
        platform="x",
        profile="x-profile",
        state=state,
        url="https://x.com/home",
        title="Home / X",
        started_at=100,
        proof_path="/app/output/runs/auth/proof.json",
    )
    assert result["proof_bundle"] == "/app/output/runs/auth/proof.json"


def test_blocked_state_requires_screenshot_in_proof_bundle():
    state = auth._state(auth.LOGIN_REQUIRED, "x_login_screen", "refresh", True)
    result = auth.build_auth_result(
        platform="x",
        profile="x-profile",
        state=state,
        url="https://x.com/i/flow/login",
        title="X",
        started_at=100,
    )
    assert result["screenshot_required"] is True
