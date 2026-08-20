# Game / GameCN 自动审查报告

- v2fly 提交：`c975ccef9c19f005a3bfa7a33255d1b406deea64`
- 自动结论：`low-risk`
- `Game.list`：188 条
- `GameCN.list`：29 条
- 无法安全转换：4 条

## 规则目标

- `Game.list` 仅承载 Epic、PlayStation、Steam、Nintendo 的非中国大陆条目，交给 `🎲 Gamer`。
- `GameCN.list` 仅承载带 `@cn` 的大陆入口；平台根域名保留后缀匹配，CDN/下载主机收紧为精确 `DOMAIN`。
- `GameCN.list` 必须放在 `Game.list` 之前；海外游戏下载继续跟随 `🎲 Gamer`。

## 无法安全转换的上游规则

| 平台 | 上游条目 | 原因 |
|---|---|---|
| `epicgames` | `regexp:^cdn\d-epicgames-\d+\.file\.myqcloud\.com$` | `unsupported-cn-regexp` |
| `epicgames` | `regexp:^epicgames-download\d-\d+\.file\.myqcloud\.com$` | `unsupported-cn-regexp` |
| `epicgames` | `regexp:^epicgames-download\d\.akamaized\.net$` | `unsupported-global-regexp` |
| `playstation` | `domain:playstation` | `single-label-domain-omitted` |