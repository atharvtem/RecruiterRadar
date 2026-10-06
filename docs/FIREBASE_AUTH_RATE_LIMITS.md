# Firebase Auth and Monthly Search Limits

RecruiterRadar can require Firebase login and limit each user to a fixed number of Tavily search attempts per UTC month.

## What Is Enforced

- Users must sign in with Google before using the Streamlit app when Firebase is configured.
- The default monthly limit is 5 Tavily search attempts per user.
- The app charges actual search attempts used by the pipeline.
- If a user has fewer than 3 searches left, the pipeline retry budget is reduced to the remaining count.
- Local spam/rule rejections that never call Tavily do not consume search budget.

## Environment Variables

```sh
FIREBASE_PROJECT_ID=
FIREBASE_WEB_API_KEY=
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REDIRECT_URI=http://localhost:8501
MONTHLY_SEARCH_LIMIT=5
```

`FIREBASE_WEB_API_KEY` is the Firebase web API key from Project Settings. It is not the same as the Firebase Admin SDK private key.
`GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` come from the Google OAuth web client used by Firebase Google sign-in.

## Firebase Console Setup

1. Create or open a Firebase project.
2. Enable Authentication.
3. Enable the Google provider.
4. Create a Firestore database.
5. In Google Cloud Console, open the OAuth web client used by Firebase and add your redirect URI:
   - Local: `http://localhost:8501`
   - Streamlit Cloud: your deployed app URL
6. Add the environment variables above to local `.env` or Streamlit secrets.

## Firestore Data Shape

Usage is stored in the `usage` collection with document IDs shaped like:

```text
{firebase_uid}_{YYYY-MM}
```

Each document stores:

```json
{
  "uid": "firebase-user-id",
  "month": "2026-10",
  "searches": 3,
  "updatedAt": "2026-10-01T16:00:00Z"
}
```

## Firestore Rules

For the current demo deployment, open Firebase Console > Firestore Database >
the `(default)` database > Rules. Replace the rules with the contents of
[`firestore.rules`](../firestore.rules) and click Publish. Do not enable public
read/write access or test mode. These rules assume Firebase-generated Google
sign-in UIDs and a limit of 5, matching `MONTHLY_SEARCH_LIMIT=5`.

The rules authorize a single-document lookup by its UID-prefixed path, including
when the document does not exist yet. Rules based on `resource.data.uid` alone
cannot authorize that first lookup. Writes validate ownership and fields, cap the
stored count at 5, and reject decreasing counts, deletes, and collection listing.

These rules do not make the current post-run counter a hard quota. Concurrent
runs can still consume Tavily calls before their usage is recorded. A hard quota
requires server-controlled atomic reservation before each Tavily request.

### Troubleshooting After Sign-In

- `PERMISSION_DENIED` / HTTP 403: check published rules, matching Firebase project
  ID, and that the Cloud Firestore API is enabled in that project.
- `UNAUTHENTICATED` / HTTP 401: sign out and sign in again; tokens from the old
  project or expired sessions will not work.
- Database `NOT_FOUND` / HTTP 404: create the `(default)` Firestore database and
  verify `FIREBASE_PROJECT_ID`. A missing individual usage document starts at zero;
  a missing database must not silently disable the quota check.

The app blocks further work if it cannot read usage, while leaving Sign out and
Retry usage check available. Publishing rules is a separate console action from
deploying Python changes; both are required.

## Implementation Files

### Developer Testing

For testing on the public deployment, keep Google sign-in enabled. Copy approved
testers' UIDs from Firebase Authentication > Users and add this top-level
Streamlit secret, then reboot:

```toml
DEVELOPER_UIDS = "first-firebase-uid,second-firebase-uid"
```

Only exact authenticated UIDs receive developer access. Emails and URL parameters
cannot enable it. Developer accounts skip Firestore quota reads/writes and have
no monthly app limit; each evaluation retains a three-search retry budget.
Provider limits still apply, and developer calls consume the shared API budget.
Remove a UID from the secret and reboot to revoke the exemption. Regular accounts
retain the five-search monthly limit. Developer usage is not recorded in Firestore.

For sign-in-free testing, use a local checkout with both `FIREBASE_PROJECT_ID` and
`FIREBASE_WEB_API_KEY` empty in the effective environment (environment overrides
Streamlit secrets, which override `.env`). Bind Streamlit to `127.0.0.1`.
Do not use this auth-disabled configuration on the public deployment. A separate
private staging deployment is optional; protect it using the hosting platform's
access control and use separate API keys to isolate testing costs.

- `app.py`: Streamlit login UI, usage display, quota block, and post-run charging.
- `recruiterradar/firebase.py`: Firebase Auth and Firestore REST helpers.
- `recruiterradar/pipeline.py`: configurable search retry budget.
- `recruiterradar/providers/live.py`: Firebase settings loaded from environment.
