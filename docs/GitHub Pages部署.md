# GitHub Pages公开演示

演示地址：https://heart06215.github.io/powang-demo/

主仓库`heart06215/media_society_comment_research`公开供比赛评审浏览，保存完整代码与开发历史。网页演示由独立部署仓库`heart06215/powang-demo`托管，仅包含生成的前端与授权展示数据，不复制主仓库历史、Python后端或本地配置。两者独立更新，主仓库的可见性调整不影响现有演示地址。

## 可用功能

公开演示支持治理总览、数据与复核总览、成本计算、7199条评论的筛选与分页、社区对比、关系图谱、三档方法看板、人工示范读取和报告数据下载。评论证据库位于可展开的“数据与复核”导航中。模型问答与服务器写入在完整版本运行；演示页对相关操作显示只读状态。

构建时移除昵称、IP、用户标识和密钥字段。部署包只包含HTML、CSS、JavaScript、图标、公开JSON快照及报告下载文件。

统计、报告、人工示范和各视频评论分别保存为独立JSON。总览与洞察首屏仅下载统计摘要，评论在进入证据库时按视频读取，关系图谱在接近视口时加载。ECharts 5.6.0与许可证随站点托管，避免外部CDN影响图表显示。

## 更新演示

在主仓库中运行：

```powershell
python scripts/prepare_github_pages.py
node tests/check_pages_runtime.cjs
python tests/check_review_ui.py
```

生成目录为`.tmp-pages-site`，已被主仓库忽略。此目录可作为公开部署仓库的独立Git工作区，构建器保留其中的`.git`目录。检查生成文件后，在该目录提交并推送到`heart06215/powang-demo`。

浏览器检查需要Playwright及本机Edge（其他系统使用Chromium），覆盖三档方法卡片、微调表的全部结果行、所有分类下拉选项、Markdown/JSON/ZIP导出、导航和评论交互。发布后可用`python tests/check_review_ui.py --base-url https://heart06215.github.io/powang-demo/`检查实际站点；该脚本阻止模型请求。

Pages设置为从公开部署仓库的`main`分支根目录发布，`.nojekyll`用于按原样托管静态文件。网站根路径固定为`/powang-demo/`；改部署仓库名称时需要同步构建器的`BASE`。

新增页面依然以主仓库`front`为源。Pages适配器在浏览器内查询下载的快照，所有显示值来自现有研究记录；它不会将静态查询伪装成实时模型回答。

## 界面与检查

演示沿用`front/base.css`与统一工作台的设计变量。使用场景为评审在浏览器中核对样本、观察结构并下载材料；采用产品界面布局，信息密度7、视觉变化6、动态强度3。只读提示沿用现有禁用状态和控件说明，不增加额外弹窗。

更新前检查评论筛选、分页、方法目标、审查读取、图谱、报告条数、公开字段和子路径导航。完整问答与标注写入继续使用本地版或支持Python的服务器。
