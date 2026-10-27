# Security policy

## Reporting a vulnerability

Do not open a public issue for security problems. Use GitHub's private
vulnerability reporting for this repository or contact the maintainer through
the repository's security contact.

## Credentials

This project does not contain or distribute API keys, passwords, or tokens.

- The Home Assistant integration stores the account credentials and API key in
  the config entry. Home Assistant controls access to `.storage`.
- The CLI reads credentials from a local `.env` file, which is ignored by git.
- Diagnostics redact the email, password, API key, and tokens.

If you believe a credential was exposed, revoke or rotate it with Charge Amps
and update the integration.
