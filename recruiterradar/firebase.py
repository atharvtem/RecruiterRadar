"""Firebase Auth and Firestore REST helpers for per-user usage limits."""

from dataclasses import dataclass
import base64
import hmac
import json
from secrets import token_urlsafe
from hashlib import sha256
from datetime import datetime, timezone
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from .providers.base import ProviderUnavailable


class FirebaseUnavailable(ProviderUnavailable):
    def __init__(self, message, *, status=None, http_status=None):
        super().__init__(message)
        self.status = status
        self.http_status = http_status


def usage_error_message(error):
    if error.status == "PERMISSION_DENIED" or error.http_status == 403:
        return ("Signed in, but Firestore denied access to your search usage. "
                "Check the published Firestore rules, Firebase project ID, and that the Firestore API is enabled.")
    if error.status == "UNAUTHENTICATED" or error.http_status == 401:
        return "Your Firebase session is no longer valid. Sign out and sign in again."
    if error.status == "NOT_FOUND" or error.http_status == 404:
        return "Firestore could not find the configured resource. Check the project ID and the (default) database."
    return "Search usage could not be loaded. Please retry; searches are blocked until usage can be checked."


@dataclass(frozen=True)
class FirebaseUser:
    uid: str
    email: str
    id_token: str
    refresh_token: str = ""


def configured(settings):
    return bool(settings.firebase_project_id and settings.firebase_web_api_key)


def is_developer(settings, user):
    return user is not None and bool(user.uid) and user.uid in settings.developer_uids


def google_configured(settings):
    return bool(configured(settings) and settings.google_client_id and settings.google_client_secret and settings.google_redirect_uri)


def clean_text(value):
    value = str(value or "").strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        value = value[1:-1].strip()
    return value


def normalize_redirect_uri(value):
    value = clean_text(value)
    if not value:
        return ""
    parsed = urlsplit(value)
    if not parsed.scheme or not parsed.netloc:
        return value.rstrip("/")
    path = parsed.path.rstrip("/")
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def redirect_uri(settings, current_url=""):
    return normalize_redirect_uri(settings.google_redirect_uri or current_url)


def month_key(now=None):
    now = now or datetime.now(timezone.utc)
    return now.strftime("%Y-%m")


def oauth_state(settings, now=None):
    timestamp = str(int(now if now is not None else time.time()))
    payload = f"{timestamp}:{token_urlsafe(18)}"
    signature = hmac.new(settings.google_client_secret.encode(), payload.encode(), sha256).hexdigest()
    return base64.urlsafe_b64encode(f"{payload}:{signature}".encode()).decode().rstrip("=")


def verify_oauth_state(settings, state, *, max_age_seconds=600, now=None):
    try:
        raw = base64.urlsafe_b64decode(state + "=" * (-len(state) % 4)).decode()
        timestamp, nonce, signature = raw.split(":", 2)
        payload = f"{timestamp}:{nonce}"
        expected = hmac.new(settings.google_client_secret.encode(), payload.encode(), sha256).hexdigest()
        age = int(now if now is not None else time.time()) - int(timestamp)
    except (ValueError, TypeError, UnicodeError):
        return False
    return hmac.compare_digest(signature, expected) and 0 <= age <= max_age_seconds


def _request_json(url, payload=None, *, bearer=None, method=None):
    headers = {"Content-Type": "application/json", "User-Agent": "RecruiterRadar/1.0"}
    if bearer:
        headers["Authorization"] = f"Bearer {bearer}"
    data = json.dumps(payload).encode() if payload is not None else None
    request = Request(url, data=data, headers=headers, method=method or ("POST" if payload is not None else "GET"))
    try:
        with urlopen(request, timeout=30) as response:
            return json.load(response)
    except HTTPError as exc:
        message = "Firebase request failed."
        status = None
        try:
            body = json.loads(exc.read().decode("utf-8", "replace"))
            error = body.get("error", {})
            if isinstance(error, dict):
                message = error.get("message") or message
                status = error.get("status")
            elif isinstance(error, str):
                message = error
        except (ValueError, UnicodeError, AttributeError):
            pass
        raise FirebaseUnavailable(message, status=status, http_status=exc.code) from None
    except (URLError, TimeoutError, OSError):
        raise FirebaseUnavailable("Firebase is unavailable. Please retry.") from None
    except (ValueError, UnicodeError):
        raise FirebaseUnavailable("Firebase returned invalid JSON. Please retry.") from None


def _auth_url(settings, method):
    return f"https://identitytoolkit.googleapis.com/v1/accounts:{method}?key={quote(settings.firebase_web_api_key)}"


def google_auth_url(settings, state):
    query = urlencode({
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "prompt": "select_account",
    })
    return f"https://accounts.google.com/o/oauth2/v2/auth?{query}"


def sign_in_with_google_code(settings, code):
    token = _request_json("https://oauth2.googleapis.com/token", {
        "code": code,
        "client_id": settings.google_client_id,
        "client_secret": settings.google_client_secret,
        "redirect_uri": settings.google_redirect_uri,
        "grant_type": "authorization_code",
    })
    id_token = token.get("id_token")
    if not id_token:
        raise FirebaseUnavailable("Google did not return an ID token. Check OAuth scopes and redirect URI.")
    response = _request_json(_auth_url(settings, "signInWithIdp"), {
        "postBody": urlencode({"id_token": id_token, "providerId": "google.com"}),
        "requestUri": settings.google_redirect_uri,
        "returnIdpCredential": True,
        "returnSecureToken": True,
    })
    return FirebaseUser(response["localId"], response.get("email", ""), response["idToken"], response.get("refreshToken", ""))


def _doc_path(settings, user, month):
    document_id = quote(f"{user.uid}_{month}", safe="")
    return ("https://firestore.googleapis.com/v1/projects/"
            f"{quote(settings.firebase_project_id)}/databases/(default)/documents/usage/{document_id}")


def _fields(document):
    fields = document.get("fields", {})
    return {
        "uid": fields.get("uid", {}).get("stringValue", ""),
        "month": fields.get("month", {}).get("stringValue", ""),
        "searches": int(fields.get("searches", {}).get("integerValue", 0)),
    }


def usage(settings, user, month=None):
    month = month or month_key()
    try:
        return _fields(_request_json(_doc_path(settings, user, month), bearer=user.id_token))
    except FirebaseUnavailable as exc:
        # A missing database is a setup error, not a fresh user's zero balance.
        missing_document = (exc.http_status == 404
                            and (str(exc) == "NOT_FOUND"
                                 or (exc.status == "NOT_FOUND"
                                     and str(exc).startswith("Document ")
                                     and "not found" in str(exc).lower())))
        if not missing_document:
            raise
        return {"uid": user.uid, "month": month, "searches": 0}


def set_usage(settings, user, searches, month=None):
    month = month or month_key()
    query = urlencode({"updateMask.fieldPaths": ["uid", "month", "searches", "updatedAt"]}, doseq=True)
    payload = {"fields": {
        "uid": {"stringValue": user.uid},
        "month": {"stringValue": month},
        "searches": {"integerValue": str(max(0, searches))},
        "updatedAt": {"timestampValue": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")},
    }}
    return _fields(_request_json(f"{_doc_path(settings, user, month)}?{query}", payload, bearer=user.id_token, method="PATCH"))


def add_searches(settings, user, count, month=None):
    current = usage(settings, user, month)
    return set_usage(settings, user, current["searches"] + max(0, count), month)
