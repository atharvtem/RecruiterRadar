# RecruiterRadar: Problems, Fixes, and Lessons

RecruiterRadar checks recruiter messages for warning signs, gathers public company evidence, and assesses job fit when the opportunity has enough support. Building it involved more than connecting an LLM to a search API. The main difficulties were measuring its decisions, keeping API usage manageable, and making authentication work consistently in a deployed app.

This document records the problems encountered during development. It distinguishes observed results from likely explanations and unfinished work. It does not imply that every change has been independently verified in the deployed environment.

## 1. A Real Company Does Not Prove a Real Offer

The central design problem was deciding what evidence actually makes a recruiter message credible. Finding an official company website is easy, but someone impersonating that company can point to the same website.

The vetting step therefore needed to look beyond company existence. It checks the message, sender affiliation, role, hiring process, payment requests, and supporting sources before assessing job fit. A strong resume match must not make a suspicious offer look legitimate.

We also needed a meaningful uncertainty outcome. Missing evidence should lead to an abstention when appropriate, rather than automatically becoming either a fraud accusation or an endorsement. Public sources still cannot prove that the person sending a message controls a particular mailbox.

**Lesson:** Define what a positive decision means before optimizing for more positive decisions. In this project, “supported” means the available evidence supports the opportunity, not that the sender has been conclusively authenticated.

## 2. Evaluating Prompts Without Spending the Search Budget

Running every experiment through live web search would consume Tavily quota. It would also make comparisons harder: the model might receive different search results in two runs, so a changed answer would not necessarily come from a better prompt.

We separated retrieval from prompt evaluation. The evaluation runner supplies fixed evidence documents to the model, allowing the baseline, few-shot, and critic variants to see the same inputs. This benchmark makes zero Tavily calls, although live LLM calls still consume provider quota.

The completed benchmark contains 25 labeled cases: 13 fraud/spam cases, 11 supported opportunities, and one case where abstention is expected. We measured fraud recall, false positives, abstention, supported-opportunity precision, and overall accuracy.

**Lesson:** Test one part of the system at a time. Fixed evidence is useful for comparing prompts, but it does not test whether live retrieval finds the right sources.

## 3. Provider Errors Were Stopping Evaluation Runs

Groq repeatedly returned HTTP 403, even after model permissions and API keys were checked. Because 403 often suggests an access problem, the initial investigation focused on account and project permissions.

During debugging, the response body showed `error code: 1010`, pointing to request filtering rather than simply an unavailable model. Adding an explicit `User-Agent: RecruiterRadar/1.0` to the HTTP requests was followed by a successful Groq-only smoke test.

The fallback path introduced a separate problem. Gemini returned HTTP 429 during longer evaluation runs. This meant the fallback had also reached a rate or quota limit; having a second provider did not guarantee that it could accept more requests.

**Lesson:** An HTTP status is a starting point, not a complete diagnosis. Inspect the provider response safely, distinguish request filtering from account permissions, and treat fallback capacity as limited too.

## 4. Interrupted Runs Needed to Resume Without Losing Comparability

Provider failures interrupted the benchmark several times. Restarting every case would waste successful calls and make a small experiment unnecessarily expensive.

The runner saves results as it progresses and preserves successful checkpoints. Rerunning against the same compatible output file retries unfinished or failed cases instead of repeating completed work.

Another error appeared during this process:

```text
Inputs changed; choose a different --output path
```

The runner fingerprints its inputs. When those inputs change, combining old and new predictions in one report can make the comparison misleading. A different output path starts a separate run; it does not automatically continue the old file. We also added a narrowly scoped Gemini-only resume path for the existing evaluation history.

**Lesson:** Resuming a run is not just about saving progress. It also requires knowing which inputs and provider configuration produced the saved results. Keep the original report and use separate output files for changed experiments.

## 5. Few-Shot Examples Helped With an Ambiguous Case

The baseline caught every fraud case in this benchmark, but it abstained on a verified stealth-startup opportunity. The supplied evidence supported the role and sender affiliation, yet the final classification remained too cautious.

Adding a few labeled examples helped the model distinguish an unsupported stealth claim from one corroborated by evidence. On this run, the few-shot variant correctly classified that case and retained the correct abstention on the genuinely uncertain case.

| Measure | Baseline | Few-shot | Few-shot + critic |
| --- | ---: | ---: | ---: |
| Accuracy | 96.0% | 100.0% | 96.0% |
| Fraud recall | 100.0% | 100.0% | 92.3% |
| False positive rate | 0.0% | 0.0% | 0.0% |
| Abstain rate | 8.0% | 4.0% | 4.0% |
| Supported-opportunity precision | 100.0% | 100.0% | 100.0% |
| LLM calls | 25 | 25 | 50 |
| Reported tokens | 15,038 | 26,311 | 58,407 |

The examples are a plausible explanation for the improved decision, but one small run is not proof of a general improvement. The four-percentage-point accuracy gain represents exactly one case out of 25. Few-shot also used more tokens, even though it required the same number of calls.

**Lesson:** Examples can clarify a difficult decision boundary, but report the number of corrected cases and the cost alongside the percentage improvement.

## 6. A Critic Agent Made the Benchmark Worse

The proposed critic was a second LLM call that reviewed the main assessment. The expectation was that a reviewer might catch mistakes before the final result reached the user.

In the completed benchmark, the critic changed a paid recruiting-platform message from suspicious to promotional. The message required payment to unlock hidden job offers. This did not become a supported opportunity, but it no longer matched the expected fraud label.

Fraud recall fell from 100% to 92.3%, and the number of model calls doubled. We kept few-shot as the production default and left the critic available as an experimental option.

**Lesson:** An additional agent can introduce errors as well as correct them. Extra complexity should earn its place through measured improvements, not through the assumption that a second opinion is always better.

## 7. The Login Screen Did Not Match the Enabled Provider

Firebase was configured for Google sign-in only, but the initial interface offered email and password. That produced `PASSWORD_LOGIN_DISABLED` and left users without the sign-in option they actually needed.

We replaced that interface with a Google authorization flow. The app exchanges Google's authorization code for a token, then uses that identity to sign in to Firebase.

**Lesson:** Authentication settings and the visible login options must agree. A working form is not useful if the backend has disabled the method it submits.

## 8. OAuth Configuration Failed in Several Different Ways

Several failures looked similar in the browser but came from different layers. Treating all of them as “Google login is broken” made troubleshooting harder.

| Error shown | What it indicated | How it was addressed |
| --- | --- | --- |
| `redirect_uri_mismatch` | The callback URL sent by the app did not match an authorized redirect URI on the selected OAuth client. | Compared the generated authorization URL with the exact client settings and standardized the deployed callback URL. |
| `org_internal` | The OAuth app was restricted to an organization. | Set up an external audience and configured test users where needed. |
| `localhost` refused to connect | The deployed login flow was returning the browser to a local address without a running server. | Used the deployed Streamlit URL for the deployed app's callback. |
| `INVALID_IDP_RESPONSE` with an audience error | Firebase did not accept the OAuth client that issued the Google token. | Aligned the OAuth client and Firebase Google provider configuration within the same project. |
| `invalid_client` | Google did not recognize the client ID sent by the app. The debug output showed a client-secret-shaped value in the client ID field. | Rechecked the distinct Client ID and Client secret values and their configuration keys. |

Firebase authorized domains and Google OAuth redirect URIs are different settings. The former takes a hostname, such as `recruiterradar.streamlit.app`; the latter takes the exact callback URL used by the app. Updating one does not replace the other.

We also made settings loading explicit across local `.env`, Streamlit secrets, and environment variables. Environment variables take precedence over Streamlit secrets, which take precedence over `.env`. This matters because a correct value in one place can still be overridden elsewhere.

After starting again with a consistent Firebase/Google Cloud setup, successful authentication was reported.

**Lesson:** Trace the values actually sent in the request. A setting that looks correct in a console is not enough if the running application is using another project, client, or configuration source.

## 9. Login State Did Not Survive the Redirect Reliably

Another failure appeared as:

```text
Login state did not match. Please try again.
```

The original flow depended on Streamlit session state surviving the trip through Google's login page. That dependency was unreliable across the redirect. We changed the state parameter to carry a timestamp and random value protected by a signature, with a limited validity period.

This removed the dependency on the original in-memory state for that check. However, a signed, time-limited state alone is not a complete replacement for binding a login attempt to the initiating browser and preventing replay. Those protections need further review, ideally using a maintained authentication library.

**Lesson:** Making a redirect succeed and fully securing an authentication flow are separate requirements. A functional workaround should not be described as a complete security solution.

## 10. Successful Sign-In Was Followed by a Database Failure

Once authentication worked, the app crashed while reading the user's Firestore usage record. The deployed traceback showed `FirebaseUnavailable`, but Streamlit redacted the underlying message.

The locked Firestore rules from the initial setup were a likely cause, although that traceback alone did not establish the exact server response. Inspection also revealed two concrete application issues: the usage read was not caught by the UI, and the old rules relied on fields in a document that would not exist for a new user.

We added rules that authorize the initial document lookup through its user-specific path. The app now catches usage-read failures, blocks further work, and keeps retry and sign-out available. Error handling also preserves HTTP/status information and distinguishes a missing usage document from a missing database. A new user's missing record can mean zero usage; a missing database is a configuration failure.

**Lesson:** Authentication proves identity; database rules separately decide what that identity may access. Test the first-ever login as well as returning users.

## 11. A Monthly Counter Is Not Yet a Strict Spending Limit

We wanted each user to have five searches per month. The first important decision was defining “search”: the app counts Tavily search attempts, not button clicks or complete opportunity evaluations. One evaluation can make several attempts, while a local rejection can make none.

Usage is stored by Firebase UID and UTC calendar month, so signing out does not reset it. The app checks the balance and limits the search budget before running. It then records consumed attempts afterward.

That final detail leaves a concurrency problem. Two requests can both read the same available balance before either writes its usage. A failed write after a search can also leave usage undercounted. Firestore rules that cap the stored number cannot undo API calls already made.

There is also duplicated configuration: `MONTHLY_SEARCH_LIMIT` controls the app, while the rules currently contain a numeric cap. Changing the intended limit requires keeping both aligned.

**Lesson:** Usage accounting and strict quota enforcement are different. A reliable limit needs an atomic, server-controlled reservation before each external search. A per-user limit also does not guarantee that the shared provider budget is sufficient for all users combined.

## 12. Developer Testing Needed a Different Allowance

Repeated testing quickly conflicts with a small monthly allowance. Disabling authentication on the public app would solve that inconvenience by removing a protection everyone relies on.

We added a server-configured allowlist of Firebase user IDs. Approved developers still sign in through Google, but skip the application's monthly quota. Each evaluation retains a bounded retry budget, and provider limits still apply. These developer searches are not currently recorded in the Firestore usage collection.

For sign-in-free testing, a local instance can run with Firebase configuration disabled and bind only to the local machine. A separate private staging deployment remains an option, rather than a requirement for the current workflow.

**Lesson:** Keep developer conveniences explicit and separate from normal user permissions. Quota exemption should not imply access to deployment settings or secrets.

## 13. A Functional Interface Still Felt Unfinished

The first login page squeezed the product name into a narrow column, causing it to break across lines. The authenticated page exposed developer configuration alongside the main workflow, used a large account alert, and gave routine actions too much visual space.

We gave the login area a stable width, removed public OAuth diagnostics, simplified the account sidebar, and grouped the workflow into Resume and Opportunity sections. We also changed Clear workspace so it preserves the authenticated user while clearing working data.

Further feedback led to removing the standalone Google logo and generic greeting. The login page now includes a short product description and getting-started steps. Privacy information remains available in the authenticated workspace.

**Lesson:** Technical correctness does not guarantee a clear experience. Real screenshots exposed layout and content problems that were not obvious from reading the code.

## What Still Needs Work

- Reserve quota atomically before each Tavily request and handle failed reservations and requests consistently.
- Review browser-bound OAuth state, replay protection, and token refresh behavior.
- Expand the benchmark with independently labeled, held-out cases and real-source evidence. The current small synthetic-evidence benchmark is not a real-world accuracy estimate.
- Evaluate live retrieval separately from fixed-evidence reasoning, using a deliberately limited search budget.
- Track developer consumption separately if it becomes a meaningful share of the API budget.
- Reduce duplicated quota configuration and verify changes in the deployed environment.

The main lesson from the project is that improvements need evidence at the right level. Better prompts need comparable evaluations, authentication needs consistent configuration across services, and a usage limit needs enforcement before the paid operation occurs.

## Supporting Files

- [Detailed prompt results](PROMPT_EVAL_RESULTS.md)
- [Authentication and usage setup](FIREBASE_AUTH_RATE_LIMITS.md)
- [Evaluation runner](../scripts/run_prompt_evals.py)
- [Firebase integration](../recruiterradar/firebase.py)
- [Firestore rules](../firestore.rules)
- [Streamlit application](../app.py)
