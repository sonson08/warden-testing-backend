# PRD: ChatGPT AI Firewall (Backend)

## 1. Overview

ChatGPT AI Firewall stops users from leaking PII and confidential information to ChatGPT. A Chrome extension intercepts the prompt before it is sent to chatgpt.com and passes it to this backend. The backend uses a local LLM (Ollama, `qwen2.5:3b`) to find sensitive data and replaces it with placeholders such as `[PERSON_1]`. When ChatGPT replies, the backend swaps the placeholders back to the real values so the user sees a normal answer.

Because the model runs locally, no sensitive data leaves the user's machine. Only the masked prompt reaches OpenAI.

This repository is the backend only. The Chrome extension is a separate project; this document defines the contract between them.

## 2. Goals

- Detect PII and confidential information in a prompt with a local LLM.
- Let the user review what was detected and choose what to mask before sending.
- Replace sensitive values with consistent, readable placeholders.
- Restore the original values in ChatGPT's responses.
- Run entirely on localhost, with nothing sensitive persisted or logged.

## 3. Non-goals

- AI tools other than ChatGPT (Claude, Gemini, Copilot, and so on).
- File uploads, images, or voice input; only typed text prompts are covered.
- Regex or rule-based detection. All detection goes through the LLM.
- Multiple users, authentication, a database, or admin policy management.
- Hosting the backend on a shared server.

## 4. Users and scenario

**Primary user:** an employee who uses ChatGPT for work and may paste customer data, internal documents, or credentials into prompts.

**Scenario:**

1. The user types "Draft an email to John Smith (john.smith@acme.com) about the Project Falcon delay" and presses Enter on chatgpt.com.
2. The extension holds the message and sends it to the backend.
3. The extension shows a preview: `John Smith` (Person), `john.smith@acme.com` (Email), `Project Falcon` (Confidential). All three are selected by default.
4. The user deselects `Project Falcon` and confirms.
5. ChatGPT receives "Draft an email to [PERSON_1] ([EMAIL_1]) about the Project Falcon delay".
6. ChatGPT replies "Hi [PERSON_1], ...". The extension sends the reply to the backend and displays "Hi John Smith, ..." instead.

## 5. Functional requirements

### 5.1 Detection

| ID   | Requirement                                                                                                                                                                                                                                        |
| ---- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| FR-1 | The backend sends the prompt to Ollama (`qwen2.5:3b`) and asks for a list of sensitive entities, each with a `type` and the exact `value` as it appears in the text.                                                                               |
| FR-2 | The request to Ollama uses structured output (a JSON schema in the `format` field) and `temperature: 0` so the response is parseable and repeatable.                                                                                               |
| FR-3 | The backend locates each returned value in the original text itself; it does not trust character offsets from the model. Values that do not appear verbatim in the text are discarded, because small models sometimes invent or paraphrase values. |
| FR-4 | Every occurrence of a detected value in the prompt is reported, not only the first.                                                                                                                                                                |
| FR-5 | Overlapping matches are resolved by keeping the longest span (for example, `John Smith` wins over `John`).                                                                                                                                         |
| FR-6 | Prompts longer than the model handles reliably are split into chunks (on paragraph or sentence boundaries), detected per chunk, and merged.                                                                                                        |
| FR-7 | If Ollama returns invalid JSON, the backend retries once, then returns an error.                                                                                                                                                                   |

### 5.2 Entity types

| Type            | Examples                                                                                                       |
| --------------- | -------------------------------------------------------------------------------------------------------------- |
| `PERSON`        | Full names, first or last names of real people                                                                 |
| `EMAIL`         | Email addresses                                                                                                |
| `PHONE`         | Phone numbers                                                                                                  |
| `ADDRESS`       | Street addresses, postal codes with street detail                                                              |
| `GOVERNMENT_ID` | SSN, passport, driver's licence, tax ID numbers                                                                |
| `FINANCIAL`     | Credit card, bank account, IBAN, routing numbers                                                               |
| `DATE_OF_BIRTH` | Birth dates tied to a person                                                                                   |
| `CREDENTIAL`    | Passwords, API keys, access tokens, private keys, connection strings                                           |
| `IP_ADDRESS`    | IPv4 and IPv6 addresses                                                                                        |
| `ORGANIZATION`  | Names of customers, clients, or partner companies                                                              |
| `CONFIDENTIAL`  | Internal project codenames, unreleased product names, internal URLs or hostnames, non-public financial figures |

### 5.3 Masking

| ID    | Requirement                                                                                                                                                               |
| ----- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| FR-8  | Each selected value is replaced with a placeholder in the form `[TYPE_N]`, for example `[PERSON_1]`, `[EMAIL_2]`.                                                         |
| FR-9  | Within one conversation, the same value always maps to the same placeholder, across all prompts in that conversation. A new value gets the next free number for its type. |
| FR-10 | Only the entities the user confirmed are masked; deselected entities stay in the text unchanged.                                                                          |
| FR-11 | The backend stores the placeholder-to-value mapping in memory, keyed by a conversation ID supplied by the extension.                                                      |

### 5.4 Unmasking

| ID    | Requirement                                                                                                                                                       |
| ----- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| FR-12 | Given a conversation ID and response text, the backend replaces every known placeholder with its original value.                                                  |
| FR-13 | Placeholder matching tolerates small changes ChatGPT may make: different letter case (`[person_1]`) and missing brackets around a known placeholder (`PERSON_1`). |
| FR-14 | Unknown placeholders, or an unknown conversation ID, leave the text unchanged; this is not an error.                                                              |
| FR-15 | Unmasking does not call the LLM; it is plain string replacement and must be fast.                                                                                 |

### 5.5 Sessions

| ID    | Requirement                                                                                                      |
| ----- | ---------------------------------------------------------------------------------------------------------------- |
| FR-16 | Mappings expire after a configurable period of inactivity (default 60 minutes) and are then removed from memory. |
| FR-17 | The extension can delete a conversation's mapping explicitly.                                                    |
| FR-18 | Mappings are lost when the server restarts. This is acceptable for the hackathon scope.                          |

## 6. API

Base path: `/api`. All bodies are JSON. Errors use the shape `{ "error": { "code": "STRING", "message": "Human readable" } }`.

### `GET /api/health`

Reports whether the backend can reach Ollama and whether the model is installed.

```json
{
  "status": "ok",
  "ollama": "reachable",
  "model": "qwen2.5:3b",
  "modelAvailable": true
}
```

### `POST /api/analyze`

Detects entities. Does not store anything.

Request:

```json
{
  "conversationId": "abc123",
  "text": "Email John Smith at john.smith@acme.com"
}
```

Response:

```json
{
  "entities": [
    {
      "id": "e1",
      "type": "PERSON",
      "value": "John Smith",
      "placeholder": "[PERSON_1]",
      "occurrences": [{ "start": 6, "end": 16 }]
    },
    {
      "id": "e2",
      "type": "EMAIL",
      "value": "john.smith@acme.com",
      "placeholder": "[EMAIL_1]",
      "occurrences": [{ "start": 20, "end": 39 }]
    }
  ]
}
```

`placeholder` is what the value would become, taking existing mappings for this conversation into account, so the preview matches the final result.

### `POST /api/mask`

Applies masking for the entities the user confirmed and saves the mapping.

Request:

```json
{
  "conversationId": "abc123",
  "text": "Email John Smith at john.smith@acme.com",
  "entities": [{ "type": "PERSON", "value": "John Smith" }]
}
```

Response:

```json
{ "maskedText": "Email [PERSON_1] at john.smith@acme.com", "maskedCount": 1 }
```

The extension sends `type` and `value` rather than IDs so this endpoint does not depend on server state from `/analyze`, and so the user could also add an entity the model missed.

### `POST /api/unmask`

Request:

```json
{
  "conversationId": "abc123",
  "text": "Hi [PERSON_1], thanks for reaching out."
}
```

Response:

```json
{ "text": "Hi John Smith, thanks for reaching out.", "replacedCount": 1 }
```

### `DELETE /api/conversations/:conversationId`

Removes the mapping for a conversation. Returns `204`.

### Error codes

| HTTP | Code                   | When                                                     |
| ---- | ---------------------- | -------------------------------------------------------- |
| 400  | `INVALID_REQUEST`      | Missing or invalid fields, or `text` over the size limit |
| 502  | `MODEL_INVALID_OUTPUT` | Ollama returned unparseable output twice                 |
| 503  | `MODEL_UNAVAILABLE`    | Ollama is unreachable or the model is not installed      |
| 504  | `MODEL_TIMEOUT`        | Ollama did not respond within the timeout                |

## 7. Extension behaviour (contract expectations)

The backend does not control these, but the extension must behave this way for the product to work:

- **Fail closed.** If `/api/analyze` fails, the extension does not send the prompt silently. It tells the user the firewall is unavailable and lets them choose to cancel or send anyway.
- **Preview.** All detected entities are selected by default. The user can deselect any of them, and send without masking only by deselecting explicitly.
- **No PII found.** If `entities` is empty, the prompt is sent without showing a preview.
- **Conversation ID.** The extension uses the ChatGPT conversation ID from the URL, or a generated ID for a new chat until ChatGPT assigns one.
- **Responses.** The extension calls `/api/unmask` after a response finishes streaming and replaces the displayed text.

## 8. Non-functional requirements

| Area              | Requirement                                                                                                                                                                                                        |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Latency           | `/api/analyze` responds in under 5 seconds for a prompt of up to 1,000 characters on a typical laptop with the model already loaded. `/api/unmask` responds in under 50 ms.                                        |
| Prompt size       | `text` is limited to 20,000 characters; longer requests are rejected with `400`.                                                                                                                                   |
| Privacy           | Prompt text, detected values, and mappings are never written to disk or to logs. Request logging records method, path, status, and timing only.                                                                    |
| Network           | The server binds to `127.0.0.1` by default. CORS allows only the configured extension origin(s).                                                                                                                   |
| Model warm-up     | On startup the backend sends a small request to Ollama so the first real prompt does not pay the model load time.                                                                                                  |
| Timeouts          | Calls to Ollama time out after a configurable limit (default 30 seconds).                                                                                                                                          |
| Detection quality | On a test set of sample prompts, the model finds at least 90% of `EMAIL`, `PHONE`, `PERSON`, and `CREDENTIAL` entities. Lower recall is acceptable for `CONFIDENTIAL` and `ORGANIZATION`, which depend on context. |

## 9. Configuration

Added to `.env.example`:

| Variable              | Default                   | Purpose                                       |
| --------------------- | ------------------------- | --------------------------------------------- |
| `PORT`                | `3000`                    | HTTP port                                     |
| `HOST`                | `127.0.0.1`               | Bind address                                  |
| `OLLAMA_HOST`         | `http://localhost:11434`  | Ollama server URL                             |
| `OLLAMA_MODEL`        | `qwen2.5:3b`              | Model used for detection                      |
| `OLLAMA_TIMEOUT_MS`   | `30000`                   | Timeout per Ollama request                    |
| `SESSION_TTL_MINUTES` | `60`                      | Inactivity period before a mapping is removed |
| `MAX_TEXT_LENGTH`     | `20000`                   | Maximum prompt size in characters             |
| `ALLOWED_ORIGINS`     | `chrome-extension://<id>` | Comma-separated CORS origins                  |

## 10. Implementation notes

The backend follows the existing project layout:

- `routes/api.js` mounts the endpoints under `/api`.
- `controllers/` holds request validation and response shaping.
- `services/ollamaService.js` calls Ollama's `/api/chat` endpoint and parses the structured output.
- `services/detectionService.js` builds the prompt, chunks long text, locates values, and resolves overlaps.
- `services/maskingService.js` assigns placeholders and performs masking and unmasking.
- `services/sessionStore.js` holds the in-memory mappings and expires them.

The detection system prompt should include the entity type list with short definitions and a few examples, and instruct the model to return values exactly as written in the input. Prompt wording will need tuning against the test set because a 3B model is sensitive to phrasing.

## 11. Known risks

| Risk                                                                        | Mitigation                                                                                   |
| --------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------- |
| A 3B model misses entities or flags harmless text                           | Preview step lets the user correct both kinds of mistake; tune the prompt against a test set |
| The model invents values that are not in the text                           | FR-3 discards any value not found verbatim                                                   |
| Detection is slow on machines without a GPU                                 | Warm-up on startup, chunking, and a clear loading state in the extension                     |
| ChatGPT rewrites or drops placeholders                                      | Tolerant matching (FR-13); remaining cases are accepted for this scope                       |
| Placeholders reveal the type of data (for example, that a name was present) | Accepted; the type helps ChatGPT give a useful answer                                        |

## 12. Success criteria for the demo

1. With Ollama running, a prompt containing a name, email, phone number, and API key is detected, previewed, masked, and sent to ChatGPT with only placeholders.
2. ChatGPT's reply is shown with the original values restored.
3. Deselecting an entity in the preview sends it unmasked.
4. Stopping Ollama makes the extension show the "firewall unavailable" warning instead of sending the prompt.

## 13. Open questions

- Should `/api/analyze` and `/api/mask` be merged into one call that also returns the default masked text, to save a round trip when the user accepts everything?
- Should users be able to add custom always-mask terms (for example, a list of client names)?
- Should the extension show a count of masked items per conversation?
