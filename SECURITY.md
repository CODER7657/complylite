# Security Policy

## Reporting a vulnerability

Please report privately; do not open a public issue.

- Preferred: GitHub private vulnerability reporting
  (Security tab, "Report a vulnerability") on this repository.
- Or email **killerff479@gmail.com** with `[COMPLYLITE SECURITY]` in the subject.

Include what you found, the affected commit, and steps to reproduce. We aim to
acknowledge within 5 working days.

## Scope

In scope: the backend API (`backend/`), the frontend (`frontend/`), the
scripts, Dockerfiles and CI workflows in this repository.

Out of scope: third-party services and dependencies (report those upstream),
and findings that need access to secrets this repository does not contain.

All data in this repository is simulated. There are no real clients, orders or
trades, and no real credentials should ever be committed. If you find one,
report it as above.
