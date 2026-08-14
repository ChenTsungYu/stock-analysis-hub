# stock-analysis-hub

## Python dependencies

This repository uses [uv](https://docs.astral.sh/uv/) for the Substack fetcher.

```bash
uv sync
uv run python -m unittest discover -s tests -v
uv run python mimiVsJamesArticles/fetch_substack.py
```

To add or update a dependency, use `uv add <package>` and commit both
`pyproject.toml` and `uv.lock`.

For local execution, copy `.env.example` to `.env` and set either
`SUBSTACK_SID` or both `SUBSTACK_EMAIL` and `SUBSTACK_PASSWORD`. The `.env`
file is ignored by Git. In GitHub Actions, the same values come from Secrets;
`SUBSTACK_SID` takes precedence if it is configured.
