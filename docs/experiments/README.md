# Experiment protocol

Every report records:

1. date, Git commit, OS, Docker version, and image digest;
2. model/version, decoding settings, context limit, and cache behavior;
3. dataset, exact task IDs, sampling, seed, and evaluator;
4. action mode, step/time/token budgets, approval policy, and network policy;
5. raw result manifest and reproduction command;
6. success, latency, tokens, retries, timeouts, and failure categories;
7. limitations and unsupported claims.

Code-action and JSON-tool comparisons may change only the action representation. Do not publish
a comparison if model, prompt content, task set, budget, or evaluator differs.
