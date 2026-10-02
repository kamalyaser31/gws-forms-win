# task.md

- [ ] in_progress: Verify the `--after` filter format live. `list_responses` sends `timestamp > "<RFC3339>"` (quoted); the Forms API docs appear to expect it unquoted. Run `form_reader.py --id <FORM_ID> --after <date>` on a form with responses, both ways, then fix `form_builder.list_responses` and add a test. Blocked on: a form ID from the user.
