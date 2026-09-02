# GoogleAI / AI 自动审查报告

- v2fly 提交：`654177bb71300a5448037afe98267c6926ef41a3`
- Sukka 对照提交：`d189f8d5d65d1b8e4bb5400fc9c6fed3cd157f45`
- 自动结论：`low-risk`
- `GoogleAI.list`：42 条
- `AI.list`：140 条
- 国内 AI 参考集合：115 条（不发布）
- 无法安全转换或需要隔离：1 条

## 路由目标

- `GoogleAI.list` 包含 Google DeepMind、Gemini、AI Studio、NotebookLM、Jules 等 Google 自有 AI 域名，固定指向 `🔍 Google`。
- `AI.list` 仅包含非 Google 的海外 AI 服务，指向 `🤖 Intelligence`。
- `category-ai-cn` 仅作为排除与审计边界，不进入海外 AI 表。
- `GoogleAI.list` 必须位于 `AI.list` 之前；两份产物不得有父子域覆盖。

## Sukka 设计对照

- Sukka 的 `ai.conf` 是人工维护的混合 AI 表，本项目只用它检查覆盖情况，不直接合并条目。
- 对照域名规则：48 条；GoogleAI 覆盖：22；AI 覆盖：22；原始范围差异：4；仍需人工：0。
- Sukka 非域名类型：`{'DOMAIN-KEYWORD': 2, 'URL-REGEX': 1}`。

## 隔离条目

| 来源 | 条目 | 原因 |
|---|---|---|
| `category-ai-!cn` | `regexp:^chatgpt-async-webps-prod-\S+-\d+\.webpubsub\.azure\.com$` | `unsupported-overseas-ai-regexp` |