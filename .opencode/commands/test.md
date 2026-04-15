---
description: Run unit tests (safe anywhere, GPIO mocked)
agent: build
---

Run the unit tests and report results.

```
uv run pytest tests/unit/ -v
```

If any tests fail, analyze the failures and suggest fixes.
