## What

<!-- One-sentence summary of the change. -->

## Why

<!-- Link to an issue or one-liner of the motivation. -->

## How

<!-- One short paragraph or a few bullets describing the implementation. -->

## Testing

- [ ] `uv run pytest` passes locally
- [ ] `uv run ruff check src/pyfintracker/ tests/` passes
- [ ] `uv run mypy src/pyfintracker/` passes
- [ ] New tests cover money/currency invariants (if touching `models.py` or migrations)
- [ ] Snapshot updated if a report output changed (`uv run pytest --snapshot-update`)

## Checklist

- [ ] Commit message follows Conventional Commits (`feat:`, `fix:`, `refactor:`, `chore:`, `ci:`, `test:`, `docs:`, `perf:`, `build:`)
- [ ] `feat!:` / `fix!:` (note the `!`) used for any breaking change
- [ ] No `float` introduced for money (Decimal only)
- [ ] No new top-level account types
- [ ] CHANGELOG.md will be updated by release-please — do not edit manually
