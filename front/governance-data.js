/* 公开报告的静态收录值；来源、口径与年份一并保存，不使用估算补齐缺失年份。 */
window.GovernanceData = Object.freeze({
  verifiedOn: "2026-10-30",
  legalVerifiedOn: "2026-11-03",
  annotationBudget: {
  "verifiedOn": "2026-11-03",
  "commentCountVerifiedAt": "2026-11-03 09:08（北京时间）",
  "commentCountField": "data.stat.reply",
  "dayWage": 150,
  "hoursPerDay": 8,
  "secondsPerItem": 60,
  "seedCount": 107,
  "reviewRate": 0.1,
  "videos": [
    {
      "bvid": "BV1fy4y1L7Rq",
      "name": "明日方舟 PV",
      "community": "二游",
      "sampleCount": 4267,
      "onlineCount": 5588105,
      "videoUrl": "https://www.bilibili.com/video/BV1fy4y1L7Rq/",
      "countUrl": "https://api.bilibili.com/x/web-interface/view?bvid=BV1fy4y1L7Rq"
    },
    {
      "bvid": "BV1h1kcBfEuJ",
      "name": "TF 家族音乐会",
      "community": "饭圈",
      "sampleCount": 2932,
      "onlineCount": 8809111,
      "videoUrl": "https://www.bilibili.com/video/BV1h1kcBfEuJ/",
      "countUrl": "https://api.bilibili.com/x/web-interface/view?bvid=BV1h1kcBfEuJ"
    }
  ]
},
  newsCases: [
  {
    "date": "2024-06-06",
    "kind": "媒体评论 · 国内",
    "title": "白玉兰奖提名争议：评论区成为攻击现场",
    "facts": "南方日报评论经新华网转载，描述《追风者》提名争议后，部分粉丝在导演、演员及出品方微博下抗议、谩骂。",
    "researchNeed": "“番位”“偷奖”等圈层叙事怎样从观点争论转为攻击，需要结合对象和上下文辨析。",
    "projectRole": "用领域词汇与六分类标签筛选相关评论，按来源检索原文，交由人工复核攻击对象和具体语境。",
    "source": "南方日报 / 新华网转载",
    "url": "https://www.news.cn/comments/20240606/655a38613e334dabb8881ea7b0017315/c.html"
  },
  {
    "date": "2025-04-02",
    "kind": "官方整治通报 · 国内",
    "title": "体育饭圈整治：线上引战与线下聚集相互交织",
    "facts": "国家网信办通报部分“粉头”账号侮辱谩骂、挑动对立，甚至组织扰乱公共秩序的线下聚集，并披露违法违规账号与群组处置情况。",
    "researchNeed": "单条口号不能证明组织关系；分散在评论、群组与事件中的线索需要逐项核验。",
    "projectRole": "汇总分类结构与时间变化，通过话术关联图和原文检索整理待核查线索，不以文本相似认定组织行为。",
    "source": "国家互联网信息办公室",
    "url": "https://www.cac.gov.cn/2025-04/02/c_1745298042333612.htm"
  },
  {
    "date": "2024-10-29",
    "kind": "媒体报道 · 韩国线下抗议",
    "title": "RIIZE 花圈抗议：线上号召延伸到线下表达",
    "facts": "央视网转载环球时报报道，描述洪承汉复出争议中的社交媒体送花圈号召、公司周边抗议及当地部门应对。",
    "researchNeed": "线上动员措辞与线下事件如何关联，需要可靠时间线、报道与原始信息，不能只靠情感标签推断。",
    "projectRole": "可将相关文本按语境归类并组织检索，供研究者比较表达类型；行为性质及线下事实仍须由外部证据核验。",
    "source": "环球时报 / 央视网转载",
    "url": "https://news.cctv.cn/2024/10/29/ARTIlpz34tsJFbyVXY2tZkEU241029.shtml"
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
