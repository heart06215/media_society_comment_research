# EdgeOne Makers 部署说明（只读演示版）

## 目标架构

```text
public/                         静态前端（EdgeOne 直接托管）
  index.html                    landing.html 的副本
  comments.html / insight.html / label.html
  base.css / governance.css / *.js
cloud-functions/
  api/[[default]].py            /api/* 的 Flask 函数（只读 + 轻量问答）
  comment_graph.py              关系图谱（仅标准库）
  rag_knowledge.py              网络用语知识库（仅标准库）
  data/                         研究快照（由 scripts/prepare_edgeone.py 生成）
  requirements.txt              只安装 flask + requests
edgeone.json                    输出目录、页面重写、函数时长
```

EdgeOne 会把 `cloud-functions/api/[[default]].py` 挂到 `/api/*`，并在调用 Flask 前去掉 `/api` 前缀。因此 Flask 内部路由是 `/videos`、`/comments`、`/analysis/<bvid>`、`/graph`、`/agent/chat`。

## 重新生成部署产物

修改 `front/` 或 `data/` 后执行：

```powershell
python scripts/prepare_edgeone.py
```

它会：

- 复制 `front/` → `public/`
- 生成 `public/index.html`
- 复制只读数据到 `cloud-functions/data/`
- 复制 `comment_graph.py`、`rag_knowledge.py`
- 生成不含 API Key 的 `cloud-functions/data/config.public.json`

## EdgeOne 控制台配置

1. 把仓库推送到 GitHub（私有仓库也可以），并授权 EdgeOne 的 GitHub App。
2. EdgeOne Makers → 新建项目 → 导入 Git 仓库 → 选择仓库和 `main` 分支。
3. 构建配置：
   - 框架预设：其他 / 静态站点
   - 构建命令：留空
   - 输出目录：`public`
   - `edgeone.json` 已声明 `outputDirectory: ./public`
4. 环境变量（按需）：
   - `ZHIPU_API_KEY`：启用 AI 问答时填写
   - `POWANG_CHAT_LIMIT`：每小时问答上限，默认 `30`
   - `POWANG_BASIC_AUTH`：可选，`user:password`。静态页面不受它保护，只保护 `/api/*`；如果需要整站访问控制，请使用 EdgeOne 的访问控制能力。
5. 加速区域：
   - 中国大陆 / 全球（含中国大陆）：**没有自定义域名时，项目域名/部署域名是一个 3 小时有效的预览链接**。适合临时评审，不适合长期公网地址。
   - 全球（不含中国大陆）：默认域名可直接访问，但中国大陆网络访问会返回 401。
6. 部署完成后从“项目概览”复制准确的预览链接。

## 只读能力

保留：

- 治理总览 `/`
- 评论证据库 `/comments`
- 社区洞察与关系图谱 `/insight`
- 标注/审查队列的读取页面 `/label`
- `/api/videos`、`/api/comments`、`/api/analysis/<bvid>`、`/api/graph`、`/api/anchors`
- `/api/agent/chat`（需 `ZHIPU_API_KEY`，有小时上限）

禁用：

- 保存锚定集、删除锚定集
- 提交二次审查
- 触发新的模型分析

这些写操作在 EdgeOne 版会返回 403，因为 Serverless 运行时的本地文件系统不是持久存储。

## 没有域名时的结论

EdgeOne 无法同时满足“没有自定义域名 + 中国大陆稳定公网访问”：

- 大陆/含大陆加速：默认域名只是 3 小时预览链接；过期返回 401。
- 全球（不含大陆）：大陆访问返回 401。
- 稳定地址需要绑定自定义域名（大陆区域还需要备案）。

如果评审必须在中国大陆长期访问且没有域名，优先考虑：

- 腾讯云轻量应用服务器 / CVM：公网 IP + `gunicorn`，访问 `http://公网IP:5000`。
- Railway / Koyeb 等提供 `*.up.railway.app`、`*.koyeb.app` 免费子域名的 Python 托管。

## 常见错误

- `404 该站点不存在`：访问的项目/部署域名不对，或项目没有成功部署。从控制台复制地址。
- `401`：预览链接过期，或全球（不含大陆）项目被大陆网络访问。
- `424 部署失败`：查看构建日志；确认输出目录为 `public`，`index.html` 存在。
- 函数 500：检查 `cloud-functions/data` 是否随部署上传，以及 `cloud-functions/requirements.txt` 是否被识别。
