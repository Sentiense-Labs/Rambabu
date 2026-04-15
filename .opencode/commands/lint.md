---
description: Format and lint the codebase
agent: build
---

Format the codebase with black, then lint with ruff. Fix any issues.

```
uv run black . && uv run ruff check
```

If ruff reports fixable issues, run `uv run ruff check --fix` and report what changed.
