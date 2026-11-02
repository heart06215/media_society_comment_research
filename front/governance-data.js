/* 公开报告的静态收录值；来源、口径与年份一并保存，不使用估算补齐缺失年份。 */
window.GovernanceData = Object.freeze({
  verifiedOn: "2026-10-30",
  legalVerifiedOn: "2026-11-02",
  ambiguityExamples: [
  {
    "key": "irony",
    "quote": "“你可真专业。”",
    "question": "是在认真夸赞，还是在表达不满？",
    "contexts": [
      {
        "title": "可能的语境 A",
        "text": "对方认真解答了问题，回复者表示感谢。字面可能与真实态度一致。"
      },
      {
        "title": "可能的语境 B",
        "text": "对方刚犯了明显错误，双方正在争论。同样的文字可能被用作反讽。"
      }
    ],
    "conclusion": "补充情境会改变理解。仍需核对实际对话，不能替说话者确定动机。"
  },
  {
    "key": "slang",
    "quote": "“这波是典。”",
    "question": "是在引用共同熟悉的梗，还是在贴标签嘲弄？",
    "contexts": [
      {
        "title": "可能的语境 A",
        "text": "熟人讨论一段经典台词，用缩略表达回应共同的文化背景。"
      },
      {
        "title": "可能的语境 B",
        "text": "争议楼层里出现同一句短评，指向对象、引用内容和语气都不完整。"
      }
    ],
    "conclusion": "查到一个梗的释义，只解决词义问题；它在本次对话中的立场仍需核验。"
  },
  {
    "key": "repeat",
    "quote": "“支持，继续。”",
    "question": "重复出现，是参与讨论，还是有组织的刷评？",
    "contexts": [
      {
        "title": "可能的语境 A",
        "text": "活动更新后，多位参与者各自表达鼓励，出现相似措辞。"
      },
      {
        "title": "可能的语境 B",
        "text": "多个楼层出现相同短句，但账号关联、发布动机与是否付费都未知。"
      }
    ],
    "conclusion": "复读不等于刷评。文本相似不足以确认组织关系、付费行为或违法事实。"
  }
],
  legislation: {
  "date": "2026-07-29",
  "verifiedOn": "2026-11-02",
  "title": "中华人民共和国反网络暴力法（征求意见稿）",
  "status": "公开征求意见文本",
  "url": "https://www.cac.gov.cn/2026-07/29/c_1787072711938509.htm",
  "note": "仅作立法进展资料，不作为生效法律依据。"
},
  economy: [
    { year: 2020, scale: 39.2, share: 38.6, shareChange: 2.4, source: "国家网信办《数字中国发展报告（2021年）》", url: "https://www.cac.gov.cn/rootimages/uploadimg/1661066515634707/1661066515634707.pdf" },
    { year: 2021, scale: 45.5, share: 39.8, shareChange: 1.2, source: "国家网信办《数字中国发展报告（2021年）》", url: "https://www.cac.gov.cn/rootimages/uploadimg/1661066515634707/1661066515634707.pdf" },
    { year: 2022, scale: 50.2, share: 41.5, shareChange: 1.7, source: "中国信通院《数字经济发展研究报告（2023年）》", url: "https://www.caict.ac.cn/kxyj/qwfb/bps/202304/P020240326636461423455.pdf" },
    { year: 2023, scale: 53.9, share: 42.8, shareChange: 1.3, source: "北京市公共数据开放平台转引中国信通院（2024年报告）", url: "https://data.beijing.gov.cn/xydt/ljhd/6cfffe0babcd4452bda0c6422798c49b.htm" },
    { year: 2024, scale: 59.2, share: 43.8, shareChange: 1.0, nominalGrowth: 9.69, source: "中国信通院《数字经济发展研究报告（2025年）》", url: "https://www.caict.ac.cn/kxyj/qwfb/bps/202603/P020260323736507370748.pdf" }
  ],
  laws: [
    { date: "2024.08.01", title: "网络暴力信息治理规定", issuer: "国家网信办等四部门", topic: "网络暴力防范", articles: "第 12、25、26、33 条", description: "研究关联：分类标准细化、证据留存与补充材料；同时注意依法监督等排除适用情形。", url: "https://www.cac.gov.cn/2024-06/14/c_1720043894161555.htm" },
    { date: "2022.12.15", title: "互联网跟帖评论服务管理规定", issuer: "国家互联网信息办公室", topic: "评论服务责任", articles: "第 4、5 条", description: "研究关联：评论服务管理与用户权益，观察评论审核、投诉举报和复核机制。", url: "https://www.cac.gov.cn/2022-11/16/c_1670253725725039.htm" },
    { date: "2020.03.01", title: "网络信息内容生态治理规定", issuer: "国家互联网信息办公室", topic: "网络生态共治", articles: "第 9、21、24 条", description: "研究关联：平台治理、侵权表达与流量造假，形成待核查的问题清单。", url: "https://www.cac.gov.cn/2019-12/20/c_1578375159509309.htm" }
  ],
  competitions: [
    {"contest": "2026 · 第十九届中国大学生软件创新大赛", "title": "PodPal 播客派", "award": "全国一等奖", "takeaway": "借鉴：先让用户看见原有操作的困难，再用直观交互解释新的处理方式。", "url": "https://sse.bjtu.edu.cn/cms/item/1127.html"},
    { contest: "2024 · 中国大学生计算机设计大赛", title: "灵犀舆情——智能舆情预警分析可视化平台", award: "全国一等奖", takeaway: "借鉴：用社区问题组织图表，把汇总数据带回具体证据。", url: "https://www.nytdc.edu.cn/jsjgcxy/2024/0904/c961a41308/page.htm" },
    { contest: "2025 · 第十四届中国软件杯", title: "面过 Mango——多模态模拟面试系统", award: "国家一等奖", takeaway: "借鉴：从使用者的难题切入，展示分析、反馈与报告产出。", url: "https://news.whu.edu.cn/info/2111/485447.htm" },
    { contest: "2026 · 中国大学生计算机设计大赛", title: "Sumisound：跨模态AI国画艺术视听基因解码与移动创作平台", award: "国家级一等奖", takeaway: "借鉴：先讲具体需求，再呈现处理流程与可落地的使用场景。", url: "https://hainan.cuc.edu.cn/2026/0903/c8811a273534/page.htm" }
  ]
});
