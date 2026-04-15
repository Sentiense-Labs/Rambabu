---
description: Check service logs on the Pi
agent: build
---

Show the latest aicar service logs.

!`journalctl -u aicar -n 30 --no-pager`

Analyze the logs for errors or warnings and summarize the service state.
