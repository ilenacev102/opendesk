## Summary of Changes
Provide a brief summary of the changes proposed in this PR.

## Architectural Checklist
- [ ] Layer rules respected: `routes/` validates & delegates; business logic lives in `services/`.
- [ ] Atomic transactions: Mutations write an audit history row in the same `BEGIN IMMEDIATE` transaction.
- [ ] UI conventions: Pure Jinja, CSS variables, CSP nonce for scripts, no raw emoji.
- [ ] Security: No secrets, credentials, or sensitive data committed.

## Testing Evidence
- [ ] Automated tests pass: `pytest tests/ -q`
- [ ] Linter is clean: `ruff check services/ routes/ utils/ tests/ app.py config.py`
- [ ] New routes/features are covered by tests (e.g. in `tests/test_auth_matrix.py`).
