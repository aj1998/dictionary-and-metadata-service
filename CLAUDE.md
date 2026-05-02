# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Implementation Guidelines
- After analysis of every task, ask all the clarifying questions (if any) to the user in one go itself.

## Operating Instructions:
1. **Context Discovery**: Always start by reading the specified plan provided to you and the relevant files mentioned in the plan.
2. **Test Driven Development**: Add a failing test before implementing any new feature or making a change. Identify the files to be modified and write tests that cover the new logic and potential edge cases. This ensures that you have a clear goal for your implementation and can verify that your changes are effective.
2. **Atomic Changes**: Implement changes one logical step at a time.
3. **Strict Adherence**: Do not deviate from the architectural decisions in the plan. If you find a technical blocker, report it back rather than guessing.
4. **Verification**: After each major change, run the relevant full build/lint/test-suite commands to ensure stability.

### Coding Conventions
- **Pattern**: Functional components with named exports.
- **Safety**: Do not modify database schemas or auth flows without an explicit approvals (if not asked by user in the start).
- **Verification**: Every change must include a successful test run before completion