# steps

Future home for built-in step implementations.

Expected modules:

- `copy_file`
- `command`
- `prompt`
- `llm`
- Evaluator or approval steps when the workflow needs them.

Do not split a step into its own module until the behavior becomes large or needs independent tests.
