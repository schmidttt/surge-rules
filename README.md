# surge-rules

为 Surge 构建可审核、可回退、按策略目标拆分的个人规则库。自动生成的
正式产物以 `v2fly/domain-list-community` 为唯一上游；Sukka 与
BlackMatrix7 只用于覆盖审计，不会把第三方成品表直接混入本仓库。Emby
规则表由仓库所有者手工维护。

当前公开十张规则表：

| 规则 | 策略目标 | 正式产物 |
|---|---|---|
| Google | 通用 Google 代理兜底 | [`rules/Google/Google.list`](rules/Google/Google.list) |
| GoogleCN | 保守的中国大陆直连入口 | [`rules/GoogleCN/GoogleCN.list`](rules/GoogleCN/GoogleCN.list) |
| GoogleAI | Google 自有 AI，固定跟随 Google 出口 | [`rules/GoogleAI/GoogleAI.list`](rules/GoogleAI/GoogleAI.list) |
| AI | 不含 Google 与中国大陆服务的海外 AI | [`rules/AI/AI.list`](rules/AI/AI.list) |
| YouTube | YouTube 专用策略 | [`rules/YouTube/YouTube.list`](rules/YouTube/YouTube.list) |
| TikTok | TikTok 专用策略 | [`rules/TikTok/TikTok.list`](rules/TikTok/TikTok.list) |
| BiliBili | BiliBili 专用策略 | [`rules/BiliBili/BiliBili.list`](rules/BiliBili/BiliBili.list) |
| Game | Epic、PlayStation、Steam、Nintendo 的海外/通用入口 | [`rules/Game/Game.list`](rules/Game/Game.list) |
| GameCN | 上述游戏平台的中国大陆入口 | [`rules/GameCN/GameCN.list`](rules/GameCN/GameCN.list) |
| Emby | 手工维护的 Emby 服务域名及精确线路 | [`rules/Emby/Emby.list`](rules/Emby/Emby.list) |

## Surge 推荐顺序

规则遵循 Surge 从上到下首次命中。广告规则应更靠前；GoogleAI 必须先于
AI，YouTube 必须先于宽泛 Google，GameCN 必须先于 Game。

```ini
# 广告与跟踪规则
RULE-SET,https://raw.githubusercontent.com/schmidttt/surge-rules/main/rules/GoogleAI/GoogleAI.list,🔍 Google,...
RULE-SET,https://raw.githubusercontent.com/schmidttt/surge-rules/main/rules/AI/AI.list,🤖 Intelligence,...
RULE-SET,https://ruleset.skk.moe/List/non_ip/apple_intelligence.conf,🍎 Apple,...
RULE-SET,https://ruleset.skk.moe/List/non_ip/apple_services.conf,🍎 Apple,...

RULE-SET,https://raw.githubusercontent.com/schmidttt/surge-rules/main/rules/YouTube/YouTube.list,📹 YouTube,...
RULE-SET,https://raw.githubusercontent.com/schmidttt/surge-rules/main/rules/GoogleCN/GoogleCN.list,DIRECT,...
RULE-SET,https://raw.githubusercontent.com/schmidttt/surge-rules/main/rules/Google/Google.list,🔍 Google,...

RULE-SET,https://raw.githubusercontent.com/schmidttt/surge-rules/main/rules/GameCN/GameCN.list,DIRECT,...
RULE-SET,https://raw.githubusercontent.com/schmidttt/surge-rules/main/rules/Game/Game.list,🎲 Gamer,...

RULE-SET,https://raw.githubusercontent.com/schmidttt/surge-rules/main/rules/TikTok/TikTok.list,📱 TikTok,...
RULE-SET,https://raw.githubusercontent.com/schmidttt/surge-rules/main/rules/BiliBili/BiliBili.list,📺 BiliBili,...
RULE-SET,https://raw.githubusercontent.com/schmidttt/surge-rules/main/rules/Emby/Emby.list,🎞️ Emby,no-resolve,extended-matching
RULE-SET,https://ruleset.skk.moe/List/non_ip/stream.conf,🎬 Streaming,...
```

GoogleAI 直接指向 `🔍 Google`，Gemini 网页、登录与 Google API 因此
天然保持同一出口，不再依赖用户手动同步两个策略组。`🤖 Intelligence`
只负责非 Google 的海外 AI 服务。

## GoogleAI 与 AI

`GoogleAI.list` 来自 v2fly `google-deepmind`，覆盖 Gemini、AI Studio、
Generative Language API、NotebookLM、Jules 等 Google 自有 AI 服务。

`AI.list` 来自 v2fly `category-ai-!cn`，生成时依次排除：

- `google-deepmind`；
- v2fly 完整 Google 域名集合能够覆盖的 Google 所有权条目；
- `category-ai-cn` 能够覆盖的中国大陆 AI 条目；
- 无法安全等价转换的 keyword/regexp。

两张表不得存在父子域覆盖。Sukka `ai.conf` 只作聚合覆盖审计；其中范围
过宽、归属不明或只适合 URL/关键词匹配的条目不会自动并入。经官方文档
或实际服务确认的精确主机可通过人工补丁加入，例如 JetBrains AI、
`g.ai` 和 `ai.com`；共享的 `api.github.com` 不会被扩大为 AI 专用规则。

## Google 与 GoogleCN

`Google.list` 是 Google 通用兜底。生成器先排除 v2fly 中可明确识别的
Google AI 和 YouTube 精确产品条目，再输出剩余 `DOMAIN` 与
`DOMAIN-SUFFIX`。父级 Google 域名仍可能覆盖产品子域，因此规则顺序
始终是最终安全边界。

`GoogleCN.list` 与 Google 共用 v2fly 解析思路，但独立生成、独立报告、
独立风险门禁，并没有合并成同一张表。GoogleCN 自动审查器只把以下条目
发布为直连规则：

- 明确带 v2fly `@cn`；
- 不属于 `@ads`、`@!cn`、Google AI、YouTube 或 Google FCM；
- 中国专属根域名，或经过显式批准的精确技术主机；
- 不属于广告统计、Crashlytics、账号或共享应用等高风险类别。

新的模糊域名只进入
[`reports/googlecn/review.md`](reports/googlecn/review.md)，不会进入正式
列表。程序会标出来源、冲突和建议；只有“本次新增待确认”需要人工处理，
历史上未变化的隔离条目不会反复阻断低风险更新。人工例外使用
`patches/googlecn/allow.txt` 和 `patches/googlecn/deny.txt`，硬安全排除
不能被补丁绕过。

海外 CI 的 DNS/HTTP 结果不能证明中国大陆可直连，因此网络探测只用于
确认文件可获取，不参与 GoogleCN 语义批准。

## Game 与 GameCN

仓库内部按 Epic、PlayStation、Steam、Nintendo 四个平台展开和统计，
最终按策略目标只输出两张表：

- `Game.list`：交给 `🎲 Gamer`，海外游戏下载继续跟随该策略。
- `GameCN.list`：固定 `DIRECT`；中国平台根域名保留后缀匹配，CDN 和
  下载主机收紧为精确 `DOMAIN`。

不生成 `GameDownload.list`。v2fly 中无法安全转换的正则只进入
[`reports/game/review.md`](reports/game/review.md)，不会为了覆盖率而放大
成整个 CDN 后缀。由于少量 GameCN 精确主机被 Game 的父域覆盖，
Surge 中必须先引用 GameCN。

## 媒体规则

- YouTube、TikTok、BiliBili 分别独立生成和审计。
- BiliBili 同时包含大陆及国际版域名，日常可选择 `DIRECT`，需要时整体
  切换香港或台湾入口。
- Emby 为手工维护列表，包含服务根域名、精确备用主机和单 IP 线路；应在
  其他国际流媒体与兜底规则之前引用。
- Sukka stream 继续处理其他国际流媒体。
- 本仓库不生成 DomesticMedia，不建议再引用 BlackMatrix7 ChinaMedia。
  国内站点由专用规则、Sukka domestic、China IP 与 GEOIP CN 接管；
  `iq.com` 等国际版服务因此可以继续进入 Streaming。

## 安全门禁

所有构建器都使用上游提交 SHA 和提交时间生成报告。所谓“固定”是指一次
运行内先解析上游分支到 SHA，再用该 SHA 下载；仓库没有宣称跨时间永远
锁定同一上游版本。

更新保护包括：

- 任何正式规则删除都必须人工审核；
- 新增数量、真实变动率和大幅变更分别设独立阈值；
- 核心域名、最小规则数、语法、重复项和文件末尾换行均会校验；
- 不支持的上游语法发生变化时必须审核；
- 九张自动生成规则表都必须生成统一 `verification` 报告；
- 只读参考源已覆盖、单一来源差异和已确认例外由程序自动处理；
- 两个以上参考源共同指出但无法确认的差异才进入人工审核；
- 人工审核集合发生变化会阻止对应规则的低风险自动合并；
- `review-required` PR 会向仓库所有者请求审核，并按风险指纹去重通知；
- GoogleAI 与 AI 的父子域覆盖、AI 中的 Google/国内 AI 泄漏会直接失败；
- 证据目录无效或精确主机决定没有落实到产物会直接失败；
- GoogleCN 新的模糊候选不会发布，并会阻止自动合并；
- Game 与 GameCN 精确重复、旧仓库大小写和无效 raw 路径会失败；
- 所有生成文件先写入暂存目录，通过校验后再逐文件替换。

具体判定流程与人工审核入口见
[`docs/rules/VERIFICATION.md`](docs/rules/VERIFICATION.md)。

仓库变量：

- `ENABLE_SCHEDULED_SYNC=true`：启用定时同步。
- `SYNC_PHASE=stable`：从观察期切换到稳定期。
- `AUTO_MERGE_LOW_RISK=true`：允许通过全部门禁的更新自动合并。

在 Google 与 AI 覆盖门禁完成试运行前，应保持
`AUTO_MERGE_LOW_RISK=false`。

## 目录

```text
surge-rules/
├── .github/workflows/
├── docs/rules/
│   ├── VERIFICATION.md
│   ├── google/
│   ├── googlecn/
│   ├── ai/
│   ├── game/
│   └── media/
├── patches/
│   ├── google/
│   ├── googlecn/
│   ├── googleai/
│   ├── ai/
│   ├── game/
│   ├── gamecn/
│   ├── youtube/
│   ├── tiktok/
│   └── bilibili/
├── reports/
├── rules/
│   ├── Google/Google.list
│   ├── GoogleCN/GoogleCN.list
│   ├── GoogleAI/GoogleAI.list
│   ├── AI/AI.list
│   ├── YouTube/YouTube.list
│   ├── TikTok/TikTok.list
│   ├── BiliBili/BiliBili.list
│   ├── Game/Game.list
│   ├── GameCN/GameCN.list
│   └── Emby/Emby.list
├── scripts/
│   ├── shared/v2fly.py
│   ├── shared/reference_verifier.py
│   ├── shared/notify_review.py
│   ├── google/build_google_rules.py
│   ├── googlecn/build_googlecn_rules.py
│   ├── ai/build_ai_rules.py
│   ├── game/build_game_rules.py
│   ├── media/build_media_rules.py
│   └── validate_repository.py
└── tests/
```

## 本地验证

```bash
python3 -m unittest discover -s tests/shared -v
python3 -m unittest discover -s tests/google -v
python3 -m unittest discover -s tests/googlecn -v
python3 -m unittest discover -s tests/ai -v
python3 -m unittest discover -s tests/game -v
python3 -m unittest discover -s tests/media -v
python3 scripts/validate_repository.py
```

从当前上游解析并固定本次构建使用的提交：

```bash
python3 scripts/google/build_google_rules.py --fetch
python3 scripts/googlecn/build_googlecn_rules.py --fetch
python3 scripts/ai/build_ai_rules.py --fetch
python3 scripts/game/build_game_rules.py --fetch
python3 scripts/media/build_media_rules.py --product youtube --fetch
python3 scripts/media/build_media_rules.py --product tiktok --fetch
python3 scripts/media/build_media_rules.py --product bilibili --fetch
```

## 正式 raw 地址

```text
https://raw.githubusercontent.com/schmidttt/surge-rules/main/rules/Google/Google.list
https://raw.githubusercontent.com/schmidttt/surge-rules/main/rules/GoogleCN/GoogleCN.list
https://raw.githubusercontent.com/schmidttt/surge-rules/main/rules/GoogleAI/GoogleAI.list
https://raw.githubusercontent.com/schmidttt/surge-rules/main/rules/AI/AI.list
https://raw.githubusercontent.com/schmidttt/surge-rules/main/rules/YouTube/YouTube.list
https://raw.githubusercontent.com/schmidttt/surge-rules/main/rules/TikTok/TikTok.list
https://raw.githubusercontent.com/schmidttt/surge-rules/main/rules/BiliBili/BiliBili.list
https://raw.githubusercontent.com/schmidttt/surge-rules/main/rules/Game/Game.list
https://raw.githubusercontent.com/schmidttt/surge-rules/main/rules/GameCN/GameCN.list
https://raw.githubusercontent.com/schmidttt/surge-rules/main/rules/Emby/Emby.list
```

## 许可

项目脚本采用 MIT。v2fly 的 MIT 许可证全文和署名单独保留。
Sukka 与 BlackMatrix7 只在线读取并生成聚合审计，不在正式产物中转载
其具体第三方规则。
