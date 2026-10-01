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

For a demo deployment:

```js
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    match /usage/{docId} {
      allow read: if request.auth != null
        && resource.data.uid == request.auth.uid;
      allow create, update: if request.auth != null
        && request.resource.data.uid == request.auth.uid;
    }
  }
}
```

This keeps normal users scoped to their own usage document. For a production-grade hard quota, move Tavily calls and counter increments behind a backend or Cloud Function transaction so clients cannot manipulate usage counters directly.

## Implementation Files

- `app.py`: Streamlit login UI, usage display, quota block, and post-run charging.
- `recruiterradar/firebase.py`: Firebase Auth and Firestore REST helpers.
- `recruiterradar/pipeline.py`: configurable search retry budget.
- `recruiterradar/providers/live.py`: Firebase settings loaded from environment.
