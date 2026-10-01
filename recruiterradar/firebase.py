"""Firebase Auth and Firestore REST helpers for per-user usage limits."""

from dataclasses import dataclass
import json
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from .providers.base import ProviderUnavailable


class FirebaseUnavailable(ProviderUnavailable):
    pass


@dataclass(frozen=True)
class FirebaseUser:
    uid: str
    email: str
    id_token: str
    refresh_token: str = ""


def configured(settings):
    return bool(settings.firebase_project_id and settings.firebase_web_api_key)


def google_configured(settings):
    return bool(configured(settings) and settings.google_client_id and settings.google_client_secret and settings.google_redirect_uri)


def month_key(now=None):
    now = now or datetime.now(timezone.utc)
    return now.strftime("%Y-%m")


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
        try:
            body = json.loads(exc.read().decode("utf-8", "replace"))
            message = body.get("error", {}).get("message") or message
        except (ValueError, UnicodeError):
            pass
        raise FirebaseUnavailable(message) from None
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
        if "NOT_FOUND" not in str(exc):
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
