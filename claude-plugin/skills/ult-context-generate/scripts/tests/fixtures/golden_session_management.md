# Digital Identity Guidelines — Session Management (Reference Excerpt)

> Source: NIST SP 800-63B, Section 7 (Session Management) — paraphrased excerpt
> for context-engineering pilot purposes. Not the verbatim standard text.

## 7.1 Session Bindings

A session binding allows access to a given set of resources without requiring
the subscriber to repeat the authentication process for each request. Session
secrets SHALL be bound to specific lifetimes, depending on the Authenticator
Assurance Level (AAL) negotiated at authentication.

### 7.1.1 Reauthentication Timeout by AAL

| AAL | Periodic Reauthentication | Inactivity Timeout |
|-----|---------------------------|---------------------|
| AAL1 | 30 days | None required |
| AAL2 | 12 hours, or 30 minutes of inactivity | 30 minutes |
| AAL3 | 12 hours, or 15 minutes of inactivity | 15 minutes |

See clause 7.2 for guidance on session termination triggers.

## 7.2 Session Termination

A session SHALL be terminated when any of the following occur:

1. The reauthentication timeout in clause 7.1.1 is reached.
2. The subscriber's credentials are revoked or expire (see clause 7.3).
3. The subscriber explicitly logs out.

Upon termination, the session secret SHALL be invalidated. A terminated
session SHALL NOT be reusable for subsequent requests.

## 7.3 Time-Bound and Guest Credentials

Where a credential is issued with a fixed expiration time (e.g., a
time-limited guest account), the session bound to that credential SHALL NOT
outlive the credential's expiration, regardless of the inactivity timeout in
clause 7.1.1. Implementations SHOULD evaluate credential expiration at the
point of session validation, not only at issuance, so that an
already-established session is terminated promptly once the credential
expires.

Cross-reference: clause 7.2 (Session Termination) governs the termination
behavior once expiration is detected.

## 7.4 Notification of Upcoming Expiration

Implementations MAY notify an administrator or the subscriber in advance of
credential expiration to allow for renewal or extension. Such notifications
are an operational consideration and are not themselves a security
requirement of this section.
