# Error Handling

Whenever you encounter an error during a task (build/test/lint/runtime/usage
issue), offer the user to save it as a rule for future sessions.

## Workflow
1. When an error occurs, briefly explain the cause and the fix.
2. Ask the user: *"Would you like to save this as a rule for future
   sessions?"*
3. If yes, create a new file under `.claude/rules/` with a descriptive
   filename:
   ```
   .claude/rules/<short-topic>.md
   ```
4. The rule file should contain:
   - A short title (the rule itself).
   - The context / when it applies.
   - The reason (what went wrong, why).
   - The corrective action / how to avoid it.

## Goal
Build up a project-specific knowledge base so that recurring errors and
their resolutions become permanent guidance.
