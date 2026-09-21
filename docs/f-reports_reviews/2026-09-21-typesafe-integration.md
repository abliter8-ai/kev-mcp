# Native TypeSafe integration — 2026-09-21

## Verified interface

[Kev's Python example](https://github.com/jaredpalmer/kev#python) uses the official `typesafe-sdk`, with `TypeSafeClient(api_key="local", base_url="http://127.0.0.1:8009", model="kev-latest")`. The SDK calls Kev's `POST /v1/systemone` endpoint and returns typed `Noul`, `Choice` and `Score` answers. This is an HTTP client connection; the SDK does not load Kev weights or select the GPU backend.

The [official Python SDK](https://github.com/typesafe-ai/typesafe-sdk-python) provides the native request and response types. The separate [System One Adapter](https://github.com/typesafe-ai/system-one-adapter-python) uses OpenAI-compatible or Anthropic LLM APIs to produce the same answer shape. It is useful for comparisons with general LLMs, but is not required to serve Kev. The MCP implementation should use the native SDK and a configured local Kev endpoint, with no automatic cloud fallback.

## Input limits

At the tested Kev source revision `4f8110a3f8620cc3a182ae9a708e4398492c4b1a`, the server uses 8,192-token state and branch limits. A branch contains the document plus one question, its options and formatting. Different questions share the document but have separate branches. This is not an 8,192-token allowance for document text alone.

Upstream encoding defaults to non-strict state handling. The MCP path must enforce strict encoding before inference, using the loaded model's tokenizer and upstream formatting. It must report an actionable error instead of silently reducing document coverage. The proposed small runtime guard preserves the native System One endpoint and adds strict preflight and capability metadata.

The current [Kev README limitations](https://github.com/jaredpalmer/kev#limitations) also distinguish serving limits from the much shorter training inputs. Neither those limits nor our short ROCm trials establish useful accuracy at maximum context.

## Design consequence

Keep the MCP bridge separate from the GPU environment. Use the official SDK for evaluation. Reuse Kev's model loading, question conversion, encoding and probability calculation. Add only the runtime checks needed for explicit input coverage, plus document tools on the MCP side.

Sources were inspected on 2026-09-21. Compatibility will be tested against pinned dependency versions during implementation; reading the SDK example is not a completed integration test.
