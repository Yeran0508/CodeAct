# M4 long-context summary comparison - 2026-11-12

## Question

Under an equal dynamic character budget, does deterministic structured summarization retain named
engineering facts better than directly middle-truncating complete step history, and what token usage
does the local provider fixture report?

## Environment and inputs

- Host: macOS 15.3.1 x86_64
- Base commit before M4-D: `a5d59cf99f2d772f1f989946ff6a1c774a734447`
- Cases: 10 deterministic histories, eight steps each
- Dynamic context budget: 2,400 characters in both modes
- Recent full steps with summary enabled: 2
- Required facts per case: one path, exact error, material decision, and unresolved item
- Stable prefix: identical SHA-256
  `1dc10d6f446425d7914127b8f0dd6cedd31297d31ce7609f781fd7b133891a47`
- Raw manifest: `docs/experiments/results/m4-summary-comparison.json`

No language model or external API is used. `regex-token-provider-v1` is a deterministic local
fixture whose documented tokenizer is `\w+|[^\w\s]`. It reports input/output/cache-read/cache-write
counts through the same ProviderUsage contract used by runtime adapters. These counts must not be
presented as OpenAI, Anthropic, or another production provider's token usage.

## Modes

- Summary off: canonical full history plus unresolved work, then deterministic middle truncation.
- Summary on: structured older-history summary plus two recent exact steps and latest observation,
  then the same deterministic truncation.
- Quality success: all four required fact strings remain present after budgeting.
- Cache: each mode starts a fresh fixture; the first request writes the fixed prefix and the next
  nine report it as cache reads.

## Reproduction

~~~bash
PYTHONPATH=backend:. python3 scripts/benchmark_m4.py \
  --cases 10 \
  --budget 2400 \
  --output docs/experiments/results/m4-summary-comparison.json
~~~

## Result

| Mode | Fact-retention success | Fixture input tokens | Cache read | Cache write |
| --- | ---: | ---: | ---: | ---: |
| Summary off | 0/10 | 13,715 | 963 | 107 |
| Summary on | 10/10 | 13,389 | 963 | 107 |

Structured summaries used 326 fewer fixture input tokens, a 2.38% reduction, while retaining all
four required fact classes in every case.

## Limitations

The cases intentionally place critical evidence where naive middle truncation removes it. The
quality result therefore validates this implementation invariant, not general reasoning quality.
The fixture tokenizer and cache are transparent test doubles, not production-provider billing or
cache evidence. A real model comparison requires fixed model/version, prompts, seeds, budgets, API
usage responses, evaluator, and repeated trials; that belongs to M5.
