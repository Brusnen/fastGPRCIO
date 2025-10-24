---
title: Contributing
---

# Contributing

Thanks for your interest in contributing! A few pointers to get started:

- Set up a Python 3.11+ environment.
- Install dev dependencies as needed for linting and tests.
- Run and edit the examples under `examples/` to validate behavior.
- Keep changes focused and add or update docs in `docs/en/` where useful.

Docs

- The docs use MkDocs Material with i18n. English is the default locale.
- Build locally with:

```bash
pip install mkdocs mkdocs-material mkdocs-static-i18n
mkdocs serve
```

Code style

- Follow existing naming and structure in `fastgrpcio/`.
- Prefer small, composable functions and clear type hints.

Thank you for making FastGRPC better!

