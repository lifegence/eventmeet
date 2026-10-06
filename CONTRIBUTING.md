# Contributing to EventMeet

Thank you for your interest. Bug reports, fixes, translations and reports from your own Zoom, Google
Workspace or Stripe setup are all welcome.

## Reporting issues

- Search the existing issues first.
- Include your Frappe version, EventMeet version (or commit), the steps to reproduce, and the related
  entries from the Error Log (remove secrets and personal data).
- Report security vulnerabilities privately as described in [SECURITY.md](SECURITY.md).

## Development setup

```bash
bench get-app https://github.com/lifegence/eventmeet   # or your fork
bench --site <site> install-app eventmeet
bench --site <site> set-config allow_tests true
bench --site <site> run-tests --app eventmeet
```

Zoom, Google and Stripe are mocked in the tests, so no accounts are needed to run them.

## Pull requests

- Keep each pull request focused on one change and describe why it is needed.
- Add or update tests for behaviour changes; the CI runs them on Frappe v15 and v16.
- Run the linters before pushing:

  ```bash
  pip install pre-commit && pre-commit install
  pre-commit run --all-files
  ```

  The CI also runs Semgrep with Frappe's rules and the project rules in `.semgrep/eventmeet.yml`.
- New guest-reachable endpoints (`allow_guest=True`) need an entry in
  [docs/security/guest-endpoint-audit.md](docs/security/guest-endpoint-audit.md) with their
  authorization, input validation and rate limit.
- User-facing strings are written in English and wrapped in `_()` / `__()`. Add the Japanese
  translation to `eventmeet/translations/ja.csv` (keep it sorted). For a word that needs a different
  translation in one DocType (for example a status), add the DocType name as the third column.
- Update the guides in both `docs/en` and `docs/ja` when you change a setup step or a label they quote.

By contributing, you agree that your contributions are licensed under the [MIT License](license.txt).
