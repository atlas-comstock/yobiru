# Waypost 互操作：在 Yobiru 投递旁边做持久协调

**状态：** 附带可运行参考实现的提案。不改动线协议、接收端和任何默认路径。

[English](WAYPOST_INTEROP.md)

## Waypost 是什么

[Waypost](https://github.com/mainline-org/waypost) 是给助手用的持久信箱加版本化源记忆服务：一个服务端保存消息、附件和资料版本，助手用限定范围的凭据、按各自游标经 HTTP 或 MCP 接入。它回答 Yobiru 有意留白的三个问题：机器离线时到了什么、一次交接的完整历史是什么、各方谈的是共享文件的哪个版本。Waypost 是 Apache-2.0，和 Yobiru 一样是 skill 驱动，同时接两边的助手不需要学新界面。

## 定位：传输旁边做协调，绝不塞进关键路径

- **Yobiru** 保持在边缘：直接投递、唤醒、单机策略、无中心存储。本文档不在 Yobiru 关键路径上加任何存储，也不改变接收端接受什么。
- **Waypost** 是旁边的 opt-in 持久层：离线缓冲、跨机器可搜索记录、版本化产物，以及一个主助手可以汇总的信箱。
- 两边各自独立工作。从不跑桥的运维者什么都察觉不到。

## 路由约定：什么情况走哪边

| 情形 | 走 |
|---|---|
| 热路径点对点投递、唤醒、夜间静音、限流 | Yobiru |
| 对方可能离线，发件方不能阻塞 | Waypost（或经桥转交） |
| 跨机器、跨多天的交接证据 | Waypost 信箱 + 回执 |
| 主助手汇总几个 worker | Waypost 信箱作为唯一收集点 |
| 双方已持有、点对点拉取的文件 | Yobiru `fetch` |
| 必须按固定版本引用的文件 | Waypost 密封 Blob / 记忆版本 |

## 寻址：两边都用 `host/agent`

代表 Yobiru 参与方的 Waypost actor，显示名就用短 Tailscale 主机名的 `host/agent` 形式，例如 `dev-server/codex`。短名每次发送都按当前 `tailscale` 状态重解析，和 Yobiru 对端解析规则一致：唯一在线匹配优先，歧义拒绝，绝不按列表顺序挑。重建机器后，先恢复选定的主机名，再指望桥接邮件找到同一个 actor。

## 信封约定：在 JSON 正文里互带 ID

绝不在信封顶层加新字段：未知字段会被接收端 400。关联 ID 走 JSON **正文**：

```json
{"type": "status", "ok": true,
 "waypost_request_id": "9f2c4e1ab07d33c5",
 "waypost_in_reply_to": "1a2b3c4d5e6f7a8b"}
```

规则：

- Yobiru 的 `reply_to` 链保持原生；桥接副本额外带 `waypost_in_reply_to`，让 Waypost 这边的 trail 同样连起来。
- Waypost 的 `request_id` 每次逻辑写入稳定，可兼去重键。Yobiru 信封 ID 可用时，参考桥从它派生固定形状的 `yb-<sha256 前 32>` 键，原 ID 留在正文里，两边记录永远能对上。
- Waypost 消息正文里的 `yobiru_id` / `yobiru_reply_to` 指回去。任一边去掉这些键都不破坏另一边自身的语义。

## 回执映射

Yobiru 跟踪状态到 Waypost 回执阶段的映射：

| Yobiru 状态 | Waypost 阶段 | 说明 |
|---|---|---|
| `received` | `received` | 只表示已存，不作更多断言 |
| `running` | `received` | 已开始不等于已处理 |
| `completed` / `failed` / `rejected` / `blocked` | `processed` | 结果放旁边一起走；Waypost 回执本身不带结果载荷 |
| `timed_out`、`late` | （无） | 未知意味着先对账，绝不自动 processed |

因此 Waypost 的 `processed` 只表示“这个 consumer 持久记录了自己的处理结果”，和 Waypost 自家 skill 契约一致——不证明远端任务成功。成功与否仍要核对证据。

## 身份与信任：硬规则

1. **发件人身份以接收端记录的 `received.peer`**（Tailscale 验证过的身份）为准，绝不能只信信封里的 `from` / `from_agent`。用自报 agent 名铸造 Waypost 身份的桥等于开了伪造口；Yobiru 自家隐私说明也写了 agent 名是路由不是隔离。
2. **桥看得到明文。** 只跑在运维者本来就信任的机器上——实践中就是运维者自己的机器，或旁边的自托管 Waypost。桥接路径适用 Waypost 已配置的隐私过滤，桥接记录保留 Waypost 审计。
3. 收到的内容两边都只是请求，永远不是批准。桥不执行消息正文，双方的唤醒和凭据规则都不变。

## 参考桥：`tools/waypost_bridge.py`

约 200 行、纯标准库的起点（Python 3.8+），单测在 `tests/test_waypost_bridge.py`：

- 轮询本机 `inbox/*.json` 记录（文档化的 `{"envelope", "received"}` 形状），按 `received.peer` 解析发送方，为每封规划一次 Waypost 发送；
- 轮询桥自己的 Waypost 信箱（HTTP），为每封规划一次 `yobiru send`；
- `--dry-run` 只规划，哪里都不真发；
- 非法 agent 名在铸造任何身份前拒绝，权限过宽的 token 文件拒绝，维护已见 ID 台账。

骨架里**明确没做**：附件转发（需要 `fetch` 加 Waypost Blob 的 prepare/PUT/commit 全程）、重试退避、守护、按空间路由、把 Waypost 回执写回 Yobiru 请求状态。每一处都在代码里标了 `TODO`。先用 `--dry-run` 跑；补完之前，任何真实运行都按实验对待。

## 有意不做的事

- 没有共享调度器、群聊 UI、恰好一次执行——两边本来就拒绝这些，桥也不加。
- 不复制唤醒：唤醒完全是 Yobiru 的事，Waypost 没有唤醒可协调。
- 两边都不改协议。回执映射如果有一天需要线支持，应该各自 SPEC 加一个简短互操作附录，而不是改消息类型。

## 希望 Yobiru 侧保持的东西

几乎没有，这正是关键：`--json` 输出稳定（已经是）、接收端记录的发送方身份（`received.peer` 已有）、文档化的收件箱记录形状（SPEC §5 已有）。这些不变，桥就不需要任何特权接口。
