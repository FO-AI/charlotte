# CLAUDE.md

## Engineering Principles

Apply these to every code change. For trivial edits (typos, one-liners), use judgment.

### Before coding
- State assumptions explicitly. If the request is ambiguous, present the interpretations and ask; don't guess.
- If a simpler approach exists, say so before implementing.
- Define what "done" means (tests pass, behavior verified) and loop until it's met.

### Architecture
- **Single responsibility:** each module, class, and function does one thing. If you need "and" to describe it, split it.
- **Clear boundaries:** separate domain logic from I/O, frameworks, and UI. Business logic must be testable without a database, network, or filesystem.
- **Dependencies point inward:** high-level logic never imports low-level details. Inject dependencies (pass them in) rather than constructing them inside.
- **Organize by feature/domain**, not by technical layer, unless the project already does otherwise.
- **Explicit interfaces:** modules communicate through small, well-named public APIs. Keep internals private.
- **Composition over inheritance.** Prefer pure functions and immutable data where practical.

### Reusability without over-engineering
- Follow existing patterns in the codebase before inventing new ones. Search for an existing utility before writing one.
- Rule of three: duplicate once, abstract on the third occurrence. Don't create abstractions for single-use code.
- No speculative features, config options, or "flexibility" that wasn't requested.
- Ask: "Would a senior engineer call this overcomplicated?" If yes, simplify.

### Readability
- Names reveal intent; no abbreviations or generic names (`data`, `temp`, `helper`, `utils`).
- Functions short enough to understand at a glance; avoid deep nesting (use early returns).
- Comments explain *why*, not *what*. Remove dead code and commented-out code.
- No magic numbers or strings; use named constants.

### Maintainability
- Make surgical changes: touch only what the task requires, match the surrounding style, and don't refactor unrelated code. Mention other problems you notice instead of fixing them.
- Handle errors at the right layer, fail loudly with useful messages, and never silently swallow exceptions. Don't add handling for impossible cases.
- Write or update tests for any changed behavior. Test behavior, not implementation details.
- Leave the code you touched at least as clean as you found it.
### Testing
- NEVER write unit tests after you write code. 
- Highly prefer E2E tests as the sole testing mechanism. Use them to verify complex features work. At the end of E2E tests, produce a verifiable and repeatable artifact. 
- If you must test a system in isolation, FIRST write all the ways it could fail, THEN write the code.
