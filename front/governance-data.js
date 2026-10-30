/* 公开报告的静态收录值；来源、口径与年份一并保存，不使用估算补齐缺失年份。 */
window.GovernanceData = Object.freeze({
  verifiedOn: "2026-10-30",
  economy: [
    { year: 2020, scale: 39.2, share: 38.6, shareChange: 2.4, source: "国家网信办《数字中国发展报告（2021年）》", url: "https://www.cac.gov.cn/rootimages/uploadimg/1661066515634707/1661066515634707.pdf" },
    { year: 2021, scale: 45.5, share: 39.8, shareChange: 1.2, source: "国家网信办《数字中国发展报告（2021年）》", url: "https://www.cac.gov.cn/rootimages/uploadimg/1661066515634707/1661066515634707.pdf" },
    { year: 2022, scale: 50.2, share: 41.5, shareChange: 1.7, source: "中国信通院《数字经济发展研究报告（2023年）》", url: "https://www.caict.ac.cn/kxyj/qwfb/bps/202304/P020240326636461423455.pdf" },
    { year: 2023, scale: 53.9, share: 42.8, shareChange: 1.3, source: "北京市公共数据开放平台转引中国信通院（2024年报告）", url: "https://data.beijing.gov.cn/xydt/ljhd/6cfffe0babcd4452bda0c6422798c49b.htm" },
    { year: 2024, scale: 59.2, share: 43.8, shareChange: 1.0, nominalGrowth: 9.69, source: "中国信通院《数字经济发展研究报告（2025年）》", url: "https://www.caict.ac.cn/kxyj/qwfb/bps/202603/P020260323736507370748.pdf" }
  ],
  laws: [
    { date: "2024.08.01", title: "网络暴力信息治理规定", issuer: "国家网信办等四部门", topic: "网络暴力防范", articles: "第 7、12、15 条", description: "研究关联：平台治理机制、识别预警与信息处置；对骂标签需结合具体语境核验。", url: "https://www.cac.gov.cn/2024-06/14/c_1720043894161555.htm" },
    { date: "2022.12.15", title: "互联网跟帖评论服务管理规定", issuer: "国家互联网信息办公室", topic: "评论服务责任", articles: "第 4、5 条", description: "研究关联：评论服务管理与用户权益，观察评论审核、投诉举报和复核机制。", url: "https://www.cac.gov.cn/2022-11/16/c_1670253725725039.htm" },
    { date: "2020.03.01", title: "网络信息内容生态治理规定", issuer: "国家互联网信息办公室", topic: "网络生态共治", articles: "第 9、21、24 条", description: "研究关联：平台治理、侵权表达与流量造假，形成待核查的问题清单。", url: "https://www.cac.gov.cn/2019-12/20/c_1578375159509309.htm" }
  ],
  competitions: [
    { contest: "2024 · 中国大学生计算机设计大赛", title: "灵犀舆情——智能舆情预警分析可视化平台", award: "全国一等奖", takeaway: "借鉴方向：围绕具体治理场景组织数据可视化。", url: "https://www.nytdc.edu.cn/jsjgcxy/2024/0904/c961a41308/page.htm" },
    { contest: "2025 · 第十四届中国软件杯", title: "面过 Mango——多模态模拟面试系统", award: "国家一等奖", takeaway: "借鉴方向：从真实需求到分析、反馈的完整服务流程。", url: "https://news.whu.edu.cn/info/2111/485447.htm" },
    { contest: "2026 · 中国大学生服务外包创新创业大赛", title: "农芯智控——智慧农业智能控制与决策系统", award: "全国赛决赛一等奖", takeaway: "借鉴方向：把技术能力落到可演示的决策支持场景。", url: "https://xxgc.hnucm.edu.cn/info/1010/6490.htm" }
  ]
});
