# File Path Handling

Whenever handling file paths, wrap them in quotes to safely handle spaces and
special characters.

## Examples (using a generic placeholder path)

- Quote when used in shell commands:
  ```bash
  cd "/Users/username/Development/Project Name/"
  ls "/Users/username/Development/Project Name/src"
  ```

- Quote inside scripts and configuration:
  ```bash
  PROJECT_DIR="/Users/username/Development/Project Name"
  cp "$PROJECT_DIR/file.txt" "$PROJECT_DIR/backup/"
  ```

- Quote in documentation, examples, and prompts.

## Rule
- Never use unquoted paths in shell commands or configuration files.
- Use the generic placeholder `/Users/username/Development/Project Name/`
  (or similar) in documentation — never the current user's actual home path.
