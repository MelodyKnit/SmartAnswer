# Source Layout

Future implementation code should live here.

Suggested split:

```text
src/
  api/
  domain/
  llm/providers/
  retrieval/
  ingestion/
  schemas/
```

Guidelines:

- keep transport logic out of retrieval and provider modules
- keep provider adapters behind stable interfaces
- keep schema definitions explicit and reusable
