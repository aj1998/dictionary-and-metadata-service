# AGENTS.md

This file provides guidance to Agents like claude-code and codex when working with code in this repository.

## Guidelines
- After analysis of every task, ask all the clarifying questions (even minor doubts) in groups (one group by one) so that the user can answer them in a continuos conversation without invalidating the prompt cache.

## Spec Creation Instruction:
- When asked for spec creations, based on the complexity of the implementation, create separate phase-wise specs in such a way that an agent implementing it should not have to delegate it to a sub-agent and the implementation can be completed in one context window itsel.
- Be modular and clear in your specs, so that lower level reasoning models can also implement them.
- Whenever you are referencing another md file in a spec, add links instead of direct text path.

## Implementation Instructions:
1. **Context Discovery**: Always start by reading the specified plan provided to you and the relevant files mentioned in the plan.
2. **Test Driven Development**: Add a failing test before implementing any new feature or making a change. Write tests that cover the new logic and potential edge cases ensuring you have a clear goal for your implementation and can verify that your changes are effective.
3. **Atomic Changes**: Implement changes one logical step at a time.
4. **Logging**: Add necessary logs for visibility/debugging in whatever you are implementing.
5. **Strict Adherence**: Do not deviate from the architectural decisions in the plan. If you find a technical blocker, report it back rather than guessing and ask user for help/clarifications.
6. **Verification**: After each major change, run the relevant full build/lint/test-suite commands to ensure stability.
7. **Updating Relevant Docs**: Always update the given spec/design doc with Implementation Notes/Diversions after the implementation.
8. **Testing**: Always add tests for new implementations. Always run full test suite of the repo after any change to check any regressions.
9. **Manual Testing Steps/Docs**: Provide the user a set of verification commands/steps so that the change can be manually tested.
10. **Pausing the implementation**: Whenever you detect that the implementation will be a long one and you require a subagent to do this, stop there. Instead of the implementation, only create phase-wise plan docs for other agents to implement including all the steps along with testing and instructions which were given to you.

### Database Safety (CRITICAL — read before running any SQL or tests)
- **`jain_kb_dev` is a LIVE database with real data — NEVER run destructive
  statements against it.** This includes `TRUNCATE`, `DROP TABLE`/`DROP ... CASCADE`,
  `DELETE`, schema `drop_all`, or anything that removes/overwrites rows. There are
  no automatic backups; a truncate is unrecoverable without a manual re-ingest.
- **Tests MUST run against `jain_kb_test`, never `jain_kb_dev`.** The test
  conftest falls back to `DATABASE_URL` when `TEST_DATABASE_URL` is unset, and the
  shell's default `DATABASE_URL` points at `jain_kb_dev` — so **always** run the
  suite with an explicit override:
  ```bash
  DATABASE_URL="postgresql+asyncpg://$(whoami)@localhost/jain_kb_test" \
    python -m pytest tests/ -q
  ```
- If a test run fails with duplicate-key / leftover-row errors, the cause is
  almost always that it ran against `jain_kb_dev`. Fix the target DB — do **not**
  truncate to "clean up".
- Any destructive DB action requires **explicit user confirmation first**, even
  during debugging, even on `_dev`/`_test` databases.

### Coding Conventions
- **Pattern**: Functional components with named exports.
- **Safety**: Do not modify database schemas or auth flows without an explicit approvals (if not asked by user in the start).
- **Verification**: Every change must include a successful test run before completion

### Token Consumption and Rate Limits Handling
- Summarize and Compact the current conversation in between any task when you feel is the right time for doing that to save tokens. Ask the user once to confirm.