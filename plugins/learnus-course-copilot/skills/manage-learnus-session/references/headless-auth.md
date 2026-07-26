# Headless authentication contract

## Lifecycle

- `start --username ID` reads the password with a hidden terminal prompt, authenticates against the current Yonsei Pass-NI SSO flow, and detaches only after LearnUs confirms a logged-in `/my/` page.
- The detached process retains the password and cookies in memory so it can rebuild the session after expiry. It does not write a cookie jar, credential file, PID file, or log.
- `status` reports local service state, the last known authentication state, and reauthentication readiness without making a remote request. It does not claim that an idle cookie is currently valid.
- `fetch` accepts only `https://ys.learnus.org/my/` or one numeric `https://ys.learnus.org/course/view.php?id=...` URL and writes the response to a mode-`0600` output file. Query strings are removed from reported effective URLs.
- `stop` ends the process, clears the retained password buffer on a best-effort basis, and removes the Unix socket.
- A reboot, process exit, or `stop` requires a new hidden password prompt.

## Security boundaries

- There is deliberately no `--password` option or password environment variable.
- The service disables core dumps where the operating system permits it.
- Its Unix socket is mode `0600`, owned by the current user, and never replaces a non-socket path or another user's socket.
- Credential submission is restricted to the fixed HTTPS Yonsei SSO host and expected Pass-NI authentication paths.
- Every request is validated before transmission and every effective response URL is validated afterward for HTTPS, port 443, no userinfo, and an approved LearnUs or Yonsei SSO host.
- Automatic redirects are rejected before they leave the approved host set. The credential-bearing authentication POST never follows redirects.
- Resource fetches and their final URLs are restricted to `ys.learnus.org`; access-denied and maintenance HTML is rejected as content, even when it carries a logged-in body class.
- CAPTCHA, MFA, credential rejection, malformed RSA data, missing SSO handoff fields, and repeated login redirects fail closed.
- The default response limit is 64 MiB and can be raised explicitly to at most 512 MiB.

The password necessarily remains readable inside the local service process while automatic reauthentication is enabled. It is never made available through the socket protocol or status output.
