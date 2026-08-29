# 生成论文插图：图1 总体框架、图2 检索逻辑、图3 残余近重复占比
# 运行：python make_paper_figures.py  → 输出到 images/
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, Rectangle, FancyBboxPatch

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei"]
plt.rcParams["axes.unicode_minus"] = False

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "images")
os.makedirs(OUT, exist_ok=True)


def fig1_architecture():
    fig, ax = plt.subplots(figsize=(10.8, 7.6), dpi=200)
    ax.set_xlim(0, 100)
    ax.set_ylim(14, 100)
    ax.axis("off")

    bands = [
        ("数据采集层", "#E8F0FE", "#3A5FA0",
         ["B站评论公开API\nmode=2 时间正序\nmode=3 热度排序",
          "多策略分层采样\n时间层＋热度层＋子评论层\n二分游标定位月份",
          "反爬与稳定采集\n登录态·随机限速\n412退避·断点续采"]),
        ("质量控制层", "#E6F4EA", "#3E8E5A",
         ["语料级近重复清洗\nbigram-Jaccard J≥0.7\n簇内保留高赞代表",
          "队列级近重复过滤\nJ≥0.55 全量比对\n排序指纹快筛",
          "标注队列分层采样\n短评25%·中评45%\n长评30%"]),
        ("标注与知识层", "#FEF6DE", "#B08A1E",
         ["锚定集人工精标\nN=200（每视频100条）\n二次审查自动回流扩充",
          "网络用语RAG知识库\n45词条·六字段结构\n关键词命中＋bigram近邻",
          "网络用语词典\n80条注入系统提示词"]),
        ("分析层", "#FDE9F0", "#B04070",
         ["锚定集检索式参考\nbigram-Jaccard 相似度\nTop-6 few-shot模板",
          "提示词工程\n四分类定义＋词典＋RAG\n结构化JSON输出",
          "大模型\nglm-4-flash→智谱SFT微调\n微调模型ID自动切换"]),
        ("应用层", "#ECECF4", "#5E5E8C",
         ["包豪斯可视化看板\n占比·趋势·词云\n态度关系图",
          "评论检索·标注·审查\nFlask API 服务",
          "LangChain洞察Agent\n六工具数据问答",
          "微调数据集导出\n智谱SFT JSONL"]),
    ]

    top, h, gap = 97.5, 14.6, 3.4
    for i, (name, face, edge, mods) in enumerate(bands):
        y0 = top - i * (h + gap) - h
        ax.add_patch(Rectangle((2, y0), 12, h, facecolor=edge, edgecolor=edge))
        ax.text(8, y0 + h / 2, name, ha="center", va="center",
                fontsize=11.5, fontweight="bold", color="white")
        n = len(mods)
        x0, x1 = 15.5, 98
        w = (x1 - x0 - 1.5 * (n - 1)) / n
        for j, text in enumerate(mods):
            bx = x0 + j * (w + 1.5)
            ax.add_patch(Rectangle((bx, y0), w, h, facecolor=face,
                                   edgecolor=edge, linewidth=1.4))
            ax.text(bx + w / 2, y0 + h / 2, text, ha="center", va="center",
                    fontsize=8.6, color="#222222", linespacing=1.55)
        if i < len(bands) - 1:
            ax.add_patch(FancyArrowPatch((50, y0 - 0.4), (50, y0 - gap + 0.4),
                                         arrowstyle="-|>", mutation_scale=16,
                                         color="#555555", linewidth=1.6))

    fig.savefig(os.path.join(OUT, "fig1_总体框架.png"),
                bbox_inches="tight", facecolor="white")
    plt.close(fig)


def _box(ax, x, y, w, h, text, face, edge, fontsize=9.2, dashed=False, bold=False):
    ax.add_patch(FancyBboxPatch(
        (x, y), w, h, boxstyle="round,pad=0.4,rounding_size=1.2",
        facecolor=face, edgecolor=edge, linewidth=1.5,
        linestyle=(0, (4, 2)) if dashed else "solid"))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center",
            fontsize=fontsize, color="#222222", linespacing=1.6,
            fontweight="bold" if bold else "normal")


def _arrow(ax, x0, y0, x1, y1, color="#555555", dashed=False):
    ax.add_patch(FancyArrowPatch(
        (x0, y0), (x1, y1), arrowstyle="-|>", mutation_scale=15,
        color=color, linewidth=1.5,
        linestyle=(0, (4, 2)) if dashed else "solid"))


def fig2_retrieval():
    """锚定集检索式参考分类流程（图2）"""
    fig, ax = plt.subplots(figsize=(8.6, 8.0), dpi=200)
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.axis("off")

    BLUE, BLUEF = "#3A5FA0", "#E8F0FE"
    GREEN, GREENF = "#3E8E5A", "#E6F4EA"
    PINK, PINKF = "#B04070", "#FDE9F0"
    GREY = "#8C8780"

    _box(ax, 27, 91, 46, 7.5, "待分类评论 x", BLUEF, BLUE, 10.5, bold=True)
    _arrow(ax, 50, 90.6, 50, 87.4)
    _box(ax, 27, 80, 46, 7.5, "归一化 → 字符 bigram 集合 G(x)", BLUEF, BLUE, 10)
    _arrow(ax, 50, 79.6, 50, 76.4)
    _box(ax, 15, 66, 70, 10,
         "与锚定集 A（200条人工精标）逐条计算 Jaccard 相似度\n"
         r"$J(x,\,x_i)=|\,G(x)\cap G(x_i)\,|\,/\,|\,G(x)\cup G(x_i)\,|$",
         GREENF, GREEN, 9.8)
    _arrow(ax, 50, 65.6, 50, 62.4)
    _box(ax, 27, 55, 46, 7.5, "按 J 排序，检索 Top-K=6 相似锚点\n（附人工确认类别）", GREENF, GREEN, 9.6)
    _arrow(ax, 50, 54.6, 50, 51.4)
    _box(ax, 33, 42, 34, 9, "最高相似度 J_max\n是否达到阈值？", "#FEF6DE", "#B08A1E", 10, bold=True)

    # 是 → 主路（左下）
    _arrow(ax, 33, 46.5, 27, 46.5, color="#3E8E5A")
    ax.text(25.5, 48.2, "是", fontsize=10.5, color="#3E8E5A", fontweight="bold", ha="center")
    _arrow(ax, 27, 46.5, 27, 34.4, color="#3E8E5A")
    _box(ax, 3, 22, 48, 12,
         "注入 Top-6 few-shot 参照模板\n＋ RAG 网络用语释义 → 提示词\n glm-4-flash / SFT 微调模型判定",
         PINKF, PINK, 9.6)
    _arrow(ax, 27, 21.6, 27, 15.4, color=PINK)
    _box(ax, 3, 6, 48, 9,
         "结构化 JSON：类别·置信度·归因·梗标签", PINKF, PINK, 9.8, bold=True)

    # 否 → 旁路（右侧虚线）
    _arrow(ax, 67, 46.5, 73, 46.5, color=GREY, dashed=True)
    ax.text(74.5, 48.2, "否", fontsize=10.5, color=GREY, fontweight="bold", ha="center")
    _arrow(ax, 73, 46.5, 73, 34.4, color=GREY, dashed=True)
    _box(ax, 56, 22, 41, 12,
         "输出低置信度\n＋“无参照样本”提示\n（诚实兜底）", "#F2F0EC", GREY, 9.6, dashed=True)

    fig.savefig(os.path.join(OUT, "fig2_检索逻辑.png"),
                bbox_inches="tight", facecolor="white")
    plt.close(fig)


def fig3_residual():
    """去重后语料的残余近重复占比（实测数据，图3）"""
    fig, ax = plt.subplots(figsize=(7.4, 4.4), dpi=200)
    thresholds = ["J≥0.5", "J≥0.6", "J≥0.7", "J≥0.8"]
    you = [11.4, 6.0, 1.0, 0.0]
    fan = [12.5, 4.1, 0.7, 0.1]
    xpos = range(len(thresholds))
    w = 0.36
    b1 = ax.bar([x - w / 2 for x in xpos], you, w,
                label="二游《明日方舟》PV（游戏圈）", color="#4A6FA5",
                edgecolor="black", linewidth=0.7)
    b2 = ax.bar([x + w / 2 for x in xpos], fan, w,
                label="饭圈TF家族音乐会（演艺圈）", color="#C2527E",
                edgecolor="black", linewidth=0.7)
    for bars in (b1, b2):
        for b in bars:
            v = b.get_height()
            ax.text(b.get_x() + b.get_width() / 2, v + 0.25, f"{v:.1f}",
                    ha="center", fontsize=9.5)
    ax.set_xticks(list(xpos))
    ax.set_xticklabels(thresholds, fontsize=11)
    ax.set_ylabel("存在近重复同伴的评论占比 / %", fontsize=10.5)
    ax.set_ylim(0, 15.5)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(fontsize=9.5, frameon=False, loc="upper right")
    ax.annotate("J≥0.8 近全同评论基本清零；\n0.5~0.7 区间为控评/刷楼\n话术的微改写变体带",
                xy=(3, 0.6), xytext=(1.85, 10.8), fontsize=9, color="#555555", ha="center",
                arrowprops=dict(arrowstyle="->", color="#888888", lw=1.0))
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "fig3_残余近重复占比.png"),
                bbox_inches="tight", facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    fig1_architecture()
    fig2_retrieval()
    fig3_residual()
    for f in sorted(os.listdir(OUT)):
        print("OK", f)
