import json
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Achievement, HskLevel, Lesson, MockTest, Question


CONTENT_DIR = Path(__file__).resolve().parent / "content"
LEVEL_CHARACTER_TOTALS = [150, 300, 600, 1200, 2500, 5000]
SORT_OFFSETS = {
    "hsk_curriculum_complete.json": 0,
    "conversation_lessons.json": 100,
    "conversation_quizzes.json": 200,
    "hsk1_reading_passages.json": 300,
}

ACHIEVEMENTS = [
    {"code": "first_quiz", "title": "First Quiz", "description": "Submit your first quiz.", "icon": "school"},
    {"code": "first_word", "title": "Word Collector", "description": "Save your first word.", "icon": "bookmark"},
    {"code": "three_lessons", "title": "Momentum", "description": "Complete three lessons.", "icon": "flame"},
]

MOCK_TESTS = [
    {
        "title": f"HSK {level} Mini Mock Test",
        "hsk_level": level,
        "duration_minutes": 15 + level * 5,
        "question_count": 15 + level * 5,
    }
    for level in range(1, 7)
] + [
    {
        "title": f"HSK {level} Skills Mix Mock Test",
        "hsk_level": level,
        "duration_minutes": 25 + level * 5,
        "question_count": 25 + level * 5,
    }
    for level in range(1, 7)
] + [
    {
        "title": f"HSK {level} Full Practice Mock Test",
        "hsk_level": level,
        "duration_minutes": 35 + level * 8,
        "question_count": 35 + level * 5,
    }
    for level in range(1, 7)
]

GENERATED_LESSONS_PER_TYPE = 14
GENERATED_LESSON_TYPES = ("mixed", "vocabulary", "grammar", "listening", "reading", "writing")

TYPE_TITLES = {
    "mixed": "Core Lesson",
    "vocabulary": "Vocabulary",
    "grammar": "Grammar",
    "listening": "Listening",
    "reading": "Reading",
    "writing": "Writing",
}

TYPE_SORT_BASE = {
    "mixed": 1000,
    "vocabulary": 2000,
    "grammar": 3000,
    "listening": 4000,
    "reading": 5000,
    "writing": 6000,
}

TOPICS = [
    {"title": "Daily Greetings", "vi": "chào hỏi hằng ngày"},
    {"title": "Family and People", "vi": "gia đình và con người"},
    {"title": "School and Study", "vi": "trường học và học tập"},
    {"title": "Food and Drink", "vi": "đồ ăn và đồ uống"},
    {"title": "Time and Schedule", "vi": "thời gian và lịch trình"},
    {"title": "Shopping and Money", "vi": "mua sắm và tiền bạc"},
    {"title": "Transport and Travel", "vi": "giao thông và du lịch"},
    {"title": "Weather and Seasons", "vi": "thời tiết và mùa"},
    {"title": "Home and Location", "vi": "nhà cửa và vị trí"},
    {"title": "Work and Plans", "vi": "công việc và kế hoạch"},
    {"title": "Health and Feelings", "vi": "sức khỏe và cảm xúc"},
    {"title": "Hobbies and Media", "vi": "sở thích và phương tiện"},
    {"title": "Requests and Help", "vi": "yêu cầu và giúp đỡ"},
    {"title": "Review Challenge", "vi": "ôn tập tổng hợp"},
]

LEVEL_WORDS = {
    1: [
        ("我", "wo3", "tôi", "I"),
        ("你", "ni3", "bạn", "you"),
        ("他", "ta1", "anh ấy", "he"),
        ("她", "ta1", "cô ấy", "she"),
        ("老师", "lao3shi1", "giáo viên", "teacher"),
        ("学生", "xue2sheng5", "học sinh", "student"),
        ("朋友", "peng2you5", "bạn bè", "friend"),
        ("名字", "ming2zi5", "tên", "name"),
        ("家", "jia1", "nhà", "home"),
        ("学校", "xue2xiao4", "trường học", "school"),
        ("水", "shui3", "nước", "water"),
        ("茶", "cha2", "trà", "tea"),
        ("米饭", "mi3fan4", "cơm", "rice"),
        ("苹果", "ping2guo3", "táo", "apple"),
        ("天气", "tian1qi4", "thời tiết", "weather"),
        ("今天", "jin1tian1", "hôm nay", "today"),
        ("明天", "ming2tian1", "ngày mai", "tomorrow"),
        ("上午", "shang4wu3", "buổi sáng", "morning"),
        ("下午", "xia4wu3", "buổi chiều", "afternoon"),
        ("喜欢", "xi3huan5", "thích", "like"),
        ("学习", "xue2xi2", "học", "study"),
        ("汉语", "Han4yu3", "tiếng Trung", "Chinese language"),
        ("书", "shu1", "sách", "book"),
        ("电脑", "dian4nao3", "máy tính", "computer"),
    ],
    2: [
        ("时间", "shi2jian1", "thời gian", "time"),
        ("问题", "wen4ti2", "vấn đề", "question"),
        ("房间", "fang2jian1", "phòng", "room"),
        ("公司", "gong1si1", "công ty", "company"),
        ("机场", "ji1chang3", "sân bay", "airport"),
        ("火车站", "huo3che1zhan4", "ga tàu", "train station"),
        ("手机", "shou3ji1", "điện thoại", "mobile phone"),
        ("颜色", "yan2se4", "màu sắc", "color"),
        ("运动", "yun4dong4", "vận động", "exercise"),
        ("旅游", "lv3you2", "du lịch", "travel"),
        ("准备", "zhun3bei4", "chuẩn bị", "prepare"),
        ("觉得", "jue2de5", "cảm thấy", "feel"),
        ("知道", "zhi1dao4", "biết", "know"),
        ("希望", "xi1wang4", "hy vọng", "hope"),
        ("帮助", "bang1zhu4", "giúp đỡ", "help"),
        ("开始", "kai1shi3", "bắt đầu", "start"),
        ("结束", "jie2shu4", "kết thúc", "finish"),
        ("可能", "ke3neng2", "có thể", "possible"),
        ("快乐", "kuai4le4", "vui vẻ", "happy"),
        ("新鲜", "xin1xian1", "tươi mới", "fresh"),
        ("便宜", "pian2yi5", "rẻ", "cheap"),
        ("贵", "gui4", "đắt", "expensive"),
        ("旁边", "pang2bian1", "bên cạnh", "beside"),
        ("一起", "yi4qi3", "cùng nhau", "together"),
    ],
    3: [
        ("安排", "an1pai2", "sắp xếp", "arrange"),
        ("会议", "hui4yi4", "cuộc họp", "meeting"),
        ("习惯", "xi2guan4", "thói quen", "habit"),
        ("环境", "huan2jing4", "môi trường", "environment"),
        ("选择", "xuan3ze2", "lựa chọn", "choice"),
        ("完成", "wan2cheng2", "hoàn thành", "complete"),
        ("复习", "fu4xi2", "ôn tập", "review"),
        ("练习", "lian4xi2", "luyện tập", "practice"),
        ("提高", "ti2gao1", "nâng cao", "improve"),
        ("经验", "jing1yan4", "kinh nghiệm", "experience"),
        ("影响", "ying3xiang3", "ảnh hưởng", "influence"),
        ("关系", "guan1xi5", "quan hệ", "relationship"),
        ("机会", "ji1hui4", "cơ hội", "opportunity"),
        ("服务", "fu2wu4", "dịch vụ", "service"),
        ("解决", "jie3jue2", "giải quyết", "solve"),
        ("决定", "jue2ding4", "quyết định", "decide"),
        ("比较", "bi3jiao4", "so sánh", "compare"),
        ("虽然", "sui1ran2", "mặc dù", "although"),
        ("但是", "dan4shi4", "nhưng", "but"),
        ("如果", "ru2guo3", "nếu", "if"),
        ("因为", "yin1wei4", "bởi vì", "because"),
        ("所以", "suo3yi3", "vì vậy", "so"),
        ("认真", "ren4zhen1", "nghiêm túc", "serious"),
        ("重要", "zhong4yao4", "quan trọng", "important"),
    ],
    4: [
        ("计划", "ji4hua4", "kế hoạch", "plan"),
        ("效率", "xiao4lv4", "hiệu suất", "efficiency"),
        ("目标", "mu4biao1", "mục tiêu", "goal"),
        ("压力", "ya1li4", "áp lực", "pressure"),
        ("文化", "wen2hua4", "văn hóa", "culture"),
        ("交流", "jiao1liu2", "giao lưu", "communicate"),
        ("资源", "zi1yuan2", "tài nguyên", "resource"),
        ("观点", "guan1dian3", "quan điểm", "viewpoint"),
        ("原因", "yuan2yin1", "nguyên nhân", "reason"),
        ("结果", "jie2guo3", "kết quả", "result"),
        ("方法", "fang1fa3", "phương pháp", "method"),
        ("能力", "neng2li4", "năng lực", "ability"),
        ("坚持", "jian1chi2", "kiên trì", "persist"),
        ("改变", "gai3bian4", "thay đổi", "change"),
        ("适应", "shi4ying4", "thích nghi", "adapt"),
        ("情况", "qing2kuang4", "tình hình", "situation"),
        ("复杂", "fu4za2", "phức tạp", "complex"),
        ("明显", "ming2xian3", "rõ ràng", "obvious"),
        ("积极", "ji1ji2", "tích cực", "positive"),
        ("负责", "fu4ze2", "phụ trách", "responsible"),
        ("讨论", "tao3lun4", "thảo luận", "discuss"),
        ("解释", "jie3shi4", "giải thích", "explain"),
        ("获得", "huo4de2", "đạt được", "obtain"),
        ("影响", "ying3xiang3", "ảnh hưởng", "influence"),
    ],
    5: [
        ("策略", "ce4lve4", "chiến lược", "strategy"),
        ("趋势", "qu1shi4", "xu hướng", "trend"),
        ("质量", "zhi4liang4", "chất lượng", "quality"),
        ("价值", "jia4zhi2", "giá trị", "value"),
        ("背景", "bei4jing3", "bối cảnh", "background"),
        ("态度", "tai4du5", "thái độ", "attitude"),
        ("标准", "biao1zhun3", "tiêu chuẩn", "standard"),
        ("过程", "guo4cheng2", "quá trình", "process"),
        ("风险", "feng1xian3", "rủi ro", "risk"),
        ("优势", "you1shi4", "lợi thế", "advantage"),
        ("限制", "xian4zhi4", "hạn chế", "limit"),
        ("需求", "xu1qiu2", "nhu cầu", "demand"),
        ("创新", "chuang4xin1", "đổi mới", "innovation"),
        ("合作", "he2zuo4", "hợp tác", "cooperate"),
        ("管理", "guan3li3", "quản lý", "manage"),
        ("观察", "guan1cha2", "quan sát", "observe"),
        ("分析", "fen1xi1", "phân tích", "analyze"),
        ("判断", "pan4duan4", "phán đoán", "judge"),
        ("表达", "biao3da2", "biểu đạt", "express"),
        ("承担", "cheng2dan1", "đảm nhận", "undertake"),
        ("促进", "cu4jin4", "thúc đẩy", "promote"),
        ("改善", "gai3shan4", "cải thiện", "improve"),
        ("保持", "bao3chi2", "duy trì", "maintain"),
        ("推动", "tui1dong4", "thúc đẩy", "drive"),
    ],
    6: [
        ("体系", "ti3xi4", "hệ thống", "system"),
        ("现象", "xian4xiang4", "hiện tượng", "phenomenon"),
        ("原则", "yuan2ze2", "nguyên tắc", "principle"),
        ("矛盾", "mao2dun4", "mâu thuẫn", "contradiction"),
        ("角度", "jiao3du4", "góc độ", "perspective"),
        ("证据", "zheng4ju4", "bằng chứng", "evidence"),
        ("结论", "jie2lun4", "kết luận", "conclusion"),
        ("效率", "xiao4lv4", "hiệu suất", "efficiency"),
        ("意识", "yi4shi2", "ý thức", "awareness"),
        ("责任", "ze2ren4", "trách nhiệm", "responsibility"),
        ("资源配置", "zi1yuan2 pei4zhi4", "phân bổ nguồn lực", "resource allocation"),
        ("长期", "chang2qi1", "dài hạn", "long term"),
        ("短期", "duan3qi1", "ngắn hạn", "short term"),
        ("评估", "ping2gu1", "đánh giá", "evaluate"),
        ("实施", "shi2shi1", "thực thi", "implement"),
        ("协调", "xie2tiao2", "phối hợp", "coordinate"),
        ("反映", "fan3ying4", "phản ánh", "reflect"),
        ("体现", "ti3xian4", "thể hiện", "embody"),
        ("引导", "yin3dao3", "dẫn dắt", "guide"),
        ("强调", "qiang2diao4", "nhấn mạnh", "emphasize"),
        ("积累", "ji1lei3", "tích lũy", "accumulate"),
        ("突破", "tu1po4", "đột phá", "breakthrough"),
        ("综合", "zong1he2", "tổng hợp", "comprehensive"),
        ("深入", "shen1ru4", "sâu sắc", "in depth"),
    ],
}

BEGINNER_GRAMMAR = [
    ("是 sentence", "A + 是 + B", "Dùng 是 để xác định danh tính, vai trò hoặc loại sự vật.", "我是学生。", "Wo3 shi4 xue2sheng5.", "Tôi là học sinh."),
    ("吗 question", "Statement + 吗?", "Thêm 吗 ở cuối câu trần thuật để tạo câu hỏi yes/no.", "你喜欢茶吗？", "Ni3 xi3huan5 cha2 ma5?", "Bạn thích trà không?"),
    ("的 possession", "Noun/pronoun + 的 + noun", "Dùng 的 để chỉ sở hữu hoặc quan hệ.", "这是我的书。", "Zhe4 shi4 wo3 de5 shu1.", "Đây là sách của tôi."),
    ("有 and 没有", "Subject + 有/没有 + object", "Dùng 有 để nói có, 没有 để nói không có.", "我有一个朋友。", "Wo3 you3 yi2 ge4 peng2you5.", "Tôi có một người bạn."),
    ("在 location", "Subject + 在 + place", "Dùng 在 trước địa điểm để nói ai/cái gì ở đâu.", "老师在学校。", "Lao3shi1 zai4 xue2xiao4.", "Giáo viên ở trường."),
    ("很 adjective", "Subject + 很 + adjective", "很 thường đứng trước tính từ trong câu miêu tả cơ bản.", "今天很热。", "Jin1tian1 hen3 re4.", "Hôm nay rất nóng."),
    ("想 plus verb", "Subject + 想 + verb", "Dùng 想 để nói mong muốn hoặc ý định.", "我想学习汉语。", "Wo3 xiang3 xue2xi2 Han4yu3.", "Tôi muốn học tiếng Trung."),
    ("会 plus skill", "Subject + 会 + verb", "Dùng 会 để nói khả năng đã học được.", "她会写汉字。", "Ta1 hui4 xie3 Han4zi4.", "Cô ấy biết viết chữ Hán."),
    ("去 plus place", "Subject + 去 + place", "Dùng 去 để nói đi đến một địa điểm.", "明天我去学校。", "Ming2tian1 wo3 qu4 xue2xiao4.", "Ngày mai tôi đi học."),
    ("几 and 多少", "几/多少 + noun", "Dùng 几 cho số nhỏ dự kiến, 多少 cho số lượng/giá cả rộng hơn.", "你家有几个人？", "Ni3 jia1 you3 ji3 ge4 ren2?", "Nhà bạn có mấy người?"),
    ("Time before action", "Time + subject + verb", "Từ chỉ thời gian thường đứng trước hoặc sau chủ ngữ.", "下午我看书。", "Xia4wu3 wo3 kan4 shu1.", "Chiều tôi đọc sách."),
    ("和 connection", "A + 和 + B", "Dùng 和 để nối danh từ hoặc người.", "我和朋友喝茶。", "Wo3 he2 peng2you5 he1 cha2.", "Tôi và bạn uống trà."),
    ("也 and 都", "Subject + 也/都 + verb/adjective", "也 nghĩa là cũng; 都 nghĩa là đều/tất cả.", "我们都学习汉语。", "Wo3men5 dou1 xue2xi2 Han4yu3.", "Chúng tôi đều học tiếng Trung."),
    ("A-not-A question", "Verb + 不 + verb", "Dùng dạng khẳng định-phủ định để hỏi lựa chọn yes/no.", "你去不去？", "Ni3 qu4 bu2 qu4?", "Bạn có đi không?"),
]

INTERMEDIATE_GRAMMAR = [
    ("了 for completion", "Verb + 了", "了 đánh dấu hành động đã hoàn thành hoặc trạng thái mới.", "我完成了练习。", "Wo3 wan2cheng2 le5 lian4xi2.", "Tôi đã hoàn thành bài luyện tập."),
    ("正在 action", "正在 + verb", "正在 nhấn mạnh hành động đang diễn ra.", "他们正在开会。", "Ta1men5 zheng4zai4 kai1hui4.", "Họ đang họp."),
    ("过 experience", "Verb + 过", "过 nói về kinh nghiệm từng làm việc gì.", "我去过中国。", "Wo3 qu4 guo5 Zhong1guo2.", "Tôi từng đi Trung Quốc."),
    ("比 comparison", "A + 比 + B + adjective", "Dùng 比 để so sánh hai đối tượng.", "今天比昨天冷。", "Jin1tian1 bi3 zuo2tian1 leng3.", "Hôm nay lạnh hơn hôm qua."),
    ("因为...所以...", "因为 + reason, 所以 + result", "Nêu nguyên nhân rồi kết quả.", "因为下雨，所以我在家复习。", "Yin1wei4 xia4yu3, suo3yi3 wo3 zai4 jia1 fu4xi2.", "Vì trời mưa nên tôi ở nhà ôn tập."),
    ("如果...就...", "如果 + condition, 就 + result", "Dùng để nói điều kiện và kết quả.", "如果你有时间，就一起练习。", "Ru2guo3 ni3 you3 shi2jian1, jiu4 yi4qi3 lian4xi2.", "Nếu bạn có thời gian thì cùng luyện tập."),
    ("虽然...但是...", "虽然 + fact, 但是 + contrast", "Diễn đạt nhượng bộ và ý tương phản.", "虽然问题难，但是我想试试。", "Sui1ran2 wen4ti2 nan2, dan4shi4 wo3 xiang3 shi4shi5.", "Mặc dù câu hỏi khó nhưng tôi muốn thử."),
    ("一边...一边...", "一边 + action, 一边 + action", "Diễn đạt hai hành động xảy ra song song.", "她一边听一边写。", "Ta1 yi4bian1 ting1 yi4bian1 xie3.", "Cô ấy vừa nghe vừa viết."),
    ("从...到...", "从 + start + 到 + end", "Nói phạm vi thời gian hoặc không gian.", "课程从九点到十点。", "Ke4cheng2 cong2 jiu3 dian3 dao4 shi2 dian3.", "Buổi học từ 9 giờ đến 10 giờ."),
    ("离 distance", "A + 离 + B + distance/adjective", "Dùng 离 để nói khoảng cách.", "学校离我家很近。", "Xue2xiao4 li2 wo3 jia1 hen3 jin4.", "Trường rất gần nhà tôi."),
    ("把 sentence", "Subject + 把 + object + verb result", "Nhấn mạnh cách xử lý đối tượng.", "我把作业写完了。", "Wo3 ba3 zuo4ye4 xie3wan2 le5.", "Tôi đã viết xong bài tập."),
    ("被 passive", "Object + 被 + actor + verb", "Dùng 被 khi đối tượng chịu tác động.", "手机被他拿走了。", "Shou3ji1 bei4 ta1 na2zou3 le5.", "Điện thoại bị anh ấy lấy đi."),
    ("越来越", "越来越 + adjective", "Diễn tả xu hướng ngày càng tăng.", "我的汉语越来越好。", "Wo3 de5 Han4yu3 yue4lai2yue4 hao3.", "Tiếng Trung của tôi ngày càng tốt."),
    ("除了...以外", "除了 + item + 以外, also/rest", "Nói ngoại trừ hoặc bổ sung ngoài một điều.", "除了阅读以外，我也练习听力。", "Chu2le5 yue4du2 yi3wai4, wo3 ye3 lian4xi2 ting1li4.", "Ngoài đọc ra, tôi cũng luyện nghe."),
]

ADVANCED_GRAMMAR = [
    ("并不是...而是...", "并不是 + A, 而是 + B", "Phủ định cách hiểu sai và đưa cách hiểu đúng hơn.", "问题并不是时间少，而是计划不清楚。", "Wen4ti2 bing4 bu2 shi4 shi2jian1 shao3, er2 shi4 ji4hua4 bu4 qing1chu5.", "Vấn đề không phải là ít thời gian mà là kế hoạch chưa rõ."),
    ("与其...不如...", "与其 + option A, 不如 + option B", "So sánh hai lựa chọn và khuyên chọn phương án sau.", "与其抱怨，不如马上行动。", "Yu3qi2 bao4yuan4, bu4ru2 ma3shang4 xing2dong4.", "Thay vì than phiền, chi bằng hành động ngay."),
    ("不仅...而且...", "不仅 + A, 而且 + B", "Nêu hai mặt, vế sau thường tăng cường ý.", "这个方法不仅有效，而且容易坚持。", "Zhe4 ge5 fang1fa3 bu4jin3 you3xiao4, er2qie3 rong2yi4 jian1chi2.", "Phương pháp này không chỉ hiệu quả mà còn dễ duy trì."),
    ("既然...就...", "既然 + fact, 就 + decision", "Dựa vào sự thật đã nêu để đưa quyết định.", "既然目标明确，就应该坚持执行。", "Ji4ran2 mu4biao1 ming2que4, jiu4 ying1gai1 jian1chi2 zhi2xing2.", "Đã rõ mục tiêu thì nên kiên trì thực hiện."),
    ("之所以...是因为...", "之所以 + result, 是因为 + reason", "Nêu kết quả trước rồi giải thích nguyên nhân.", "他之所以进步快，是因为每天复盘。", "Ta1 zhi1suo3yi3 jin4bu4 kuai4, shi4 yin1wei4 mei3tian1 fu4pan2.", "Anh ấy tiến bộ nhanh là vì mỗi ngày đều tổng kết."),
    ("无论...都...", "无论 + condition, 都 + result", "Diễn đạt bất kể điều kiện nào kết quả vẫn không đổi.", "无论多忙，我都坚持阅读。", "Wu2lun4 duo1 mang2, wo3 dou1 jian1chi2 yue4du2.", "Dù bận thế nào tôi vẫn kiên trì đọc."),
    ("除非...否则...", "除非 + condition, 否则 + consequence", "Nêu điều kiện duy nhất để tránh kết quả khác.", "除非提前准备，否则很难通过考试。", "Chu2fei1 ti2qian2 zhun3bei4, fou3ze2 hen3 nan2 tong1guo4 kao3shi4.", "Trừ khi chuẩn bị trước, nếu không rất khó qua kỳ thi."),
    ("一旦...就...", "一旦 + event, 就 + result", "Nói khi một việc xảy ra thì kết quả sẽ lập tức theo sau.", "一旦形成习惯，就更容易坚持。", "Yi2dan4 xing2cheng2 xi2guan4, jiu4 geng4 rong2yi4 jian1chi2.", "Một khi hình thành thói quen thì dễ kiên trì hơn."),
    ("宁可...也不...", "宁可 + sacrifice, 也不 + unacceptable action", "Chọn hy sinh một điều hơn là làm điều không muốn.", "他宁可多练一小时，也不放弃目标。", "Ta1 ning4ke3 duo1 lian4 yi4 xiao3shi2, ye3 bu2 fang4qi4 mu4biao1.", "Anh ấy thà luyện thêm một giờ chứ không bỏ mục tiêu."),
    ("反而", "Clause + 反而 + opposite result", "Diễn đạt kết quả trái với dự đoán.", "方法太多，反而让人难以选择。", "Fang1fa3 tai4 duo1, fan3er2 rang4 ren2 nan2yi3 xuan3ze2.", "Quá nhiều phương pháp lại khiến người ta khó chọn."),
    ("由此可见", "Evidence. 由此可见 + conclusion", "Dùng để rút ra kết luận từ thông tin trước.", "数据明显提高。由此可见，计划有效。", "Shu4ju4 ming2xian3 ti2gao1. You2ci3 ke3jian4, ji4hua4 you3xiao4.", "Dữ liệu tăng rõ rệt. Từ đó có thể thấy kế hoạch hiệu quả."),
    ("在...方面", "在 + domain + 方面", "Giới hạn phạm vi thảo luận.", "在听力方面，他进步最快。", "Zai4 ting1li4 fang1mian4, ta1 jin4bu4 zui4 kuai4.", "Về mặt nghe, anh ấy tiến bộ nhanh nhất."),
    ("从...来看", "从 + perspective + 来看", "Nêu góc nhìn dùng để đánh giá.", "从长期来看，积累比速度更重要。", "Cong2 chang2qi1 lai2 kan4, ji1lei3 bi3 su4du4 geng4 zhong4yao4.", "Nhìn dài hạn, tích lũy quan trọng hơn tốc độ."),
    ("值得", "值得 + verb", "Nói việc gì đáng làm.", "这个经验值得记录。", "Zhe4 ge5 jing1yan4 zhi2de2 ji4lu4.", "Kinh nghiệm này đáng ghi lại."),
]

GRAMMAR_PATTERNS = {
    1: BEGINNER_GRAMMAR,
    2: BEGINNER_GRAMMAR,
    3: INTERMEDIATE_GRAMMAR,
    4: INTERMEDIATE_GRAMMAR,
    5: ADVANCED_GRAMMAR,
    6: ADVANCED_GRAMMAR,
}

PRONOUN_WORDS = {"我", "你", "他", "她"}
TIME_WORDS = {"今天", "明天", "上午", "下午", "时间", "长期", "短期"}
CONNECTOR_WORDS = {"虽然", "但是", "如果", "因为", "所以"}
PLACE_WORDS = {"家", "学校", "房间", "公司", "机场", "火车站", "旁边"}
VERB_WORDS = {
    "喜欢",
    "学习",
    "准备",
    "觉得",
    "知道",
    "希望",
    "帮助",
    "开始",
    "结束",
    "旅游",
    "安排",
    "完成",
    "复习",
    "练习",
    "提高",
    "解决",
    "决定",
    "坚持",
    "改变",
    "适应",
    "讨论",
    "解释",
    "获得",
    "合作",
    "管理",
    "观察",
    "分析",
    "判断",
    "表达",
    "承担",
    "促进",
    "改善",
    "保持",
    "推动",
    "评估",
    "实施",
    "协调",
    "反映",
    "体现",
    "引导",
    "强调",
    "积累",
    "突破",
    "深入",
}
ADJECTIVE_WORDS = {
    "可能",
    "快乐",
    "新鲜",
    "便宜",
    "贵",
    "认真",
    "重要",
    "复杂",
    "明显",
    "积极",
    "负责",
    "综合",
}


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _hsk_level_number(value: Any) -> int:
    if isinstance(value, int):
        return value
    return int(str(value).upper().replace("HSK", ""))


def _meaning(english: str | None, vietnamese: str | None) -> str:
    return " / ".join(part for part in (english, vietnamese) if part)


def _translations(en: str | None = None, vi: str | None = None) -> dict[str, str]:
    return {key: value for key, value in {"en": en, "vi": vi}.items() if value}


def _chinese_entry(hanzi: str, pinyin: str = "", meaning: str = "") -> dict[str, str]:
    entry = {"hanzi": hanzi}
    if pinyin:
        entry["pinyin"] = pinyin
    if meaning:
        entry["meaning"] = meaning
    return entry


def _rich_lessons() -> list[dict[str, Any]]:
    path = CONTENT_DIR / "hsk_core_curriculum.json"
    if not path.exists():
        return []
    data = _load_json(path)
    lessons: list[dict[str, Any]] = []
    for level in data.get("levels", []):
        for lesson in level.get("lessons", []):
            lessons.append(lesson)
    return lessons


def _external_vocabulary_entries(lesson: dict[str, Any]) -> list[dict[str, Any]]:
    level = int(lesson["hsk_level"])
    category = lesson.get("title", "").split(": ", 1)[-1] or TYPE_TITLES.get(lesson.get("lesson_type", ""), "Lesson")
    entries = []
    for item in lesson.get("vocabulary_list", []):
        hanzi = item.get("hanzi", "")
        if not hanzi:
            continue
        entry = {
            "hanzi": hanzi,
            "pinyin": item.get("pinyin", ""),
            "meaning": item.get("meaning_vi") or item.get("meaning_en", ""),
            "meaning_vi": item.get("meaning_vi", ""),
            "meaning_en": item.get("meaning_en", ""),
            "translations": _translations(item.get("meaning_en"), item.get("meaning_vi")),
            "word_type": _word_type(hanzi),
            "category": category,
            "hsk_level": level,
        }
        if item.get("example_en") or item.get("example_vi"):
            entry["example_translations"] = _translations(item.get("example_en"), item.get("example_vi"))
        for key in ("example_cn", "example_pinyin", "example_vi", "example_en", "usage_note"):
            if item.get(key):
                entry[key] = item[key]
        entries.append(entry)
    return entries


def _external_grammar_points(lesson: dict[str, Any]) -> list[dict[str, Any]]:
    points = []
    for item in lesson.get("grammar_points", []):
        title = item.get("point") or item.get("title", "")
        if not title:
            continue
        usage = item.get("usage_vi") or item.get("usage_en") or item.get("explanation", "")
        usage_en = item.get("usage_en") or item.get("explanation_en")
        usage_vi = item.get("usage_vi") or item.get("explanation_vi") or usage
        structure = item.get("structure") or ""
        points.append(
            {
                "title": title,
                "title_translations": _translations(title, title),
                "structure": structure,
                "explanation": usage or structure or title,
                "explanation_translations": _translations(usage_en or usage, usage_vi),
                "examples": [
                    {
                        **_chinese_entry(
                            example.get("hanzi", example.get("Chinese", "")),
                            example.get("pinyin", example.get("Pinyin", "")),
                            example.get("meaning_vi", example.get("Vietnamese", ""))
                            or example.get("meaning_en", example.get("English", "")),
                        ),
                        "meaning_vi": example.get("meaning_vi", example.get("Vietnamese", "")),
                        "meaning_en": example.get("meaning_en", example.get("English", "")),
                        "translations": _translations(
                            example.get("meaning_en", example.get("English", "")),
                            example.get("meaning_vi", example.get("Vietnamese", "")),
                        ),
                    }
                    for example in item.get("examples", [])
                    if isinstance(example, dict)
                    and (example.get("hanzi") or example.get("Chinese"))
                ],
            }
        )
    return points


def _external_text_entry(raw: dict[str, Any]) -> dict[str, Any] | None:
    chinese = raw.get("chinese", "")
    if not chinese:
        return None
    return {
        **_chinese_entry(chinese, raw.get("pinyin", ""), raw.get("vietnamese") or raw.get("english", "")),
        "meaning_vi": raw.get("vietnamese", ""),
        "meaning_en": raw.get("english", ""),
        "translations": _translations(raw.get("english"), raw.get("vietnamese")),
    }


def _external_question_prompt(question: dict[str, Any]) -> str:
    prompt = question.get("prompt", "")
    if question.get("audio_text"):
        prompt = f"{prompt}\nAudio: {question['audio_text']}"
    if question.get("image_keyword"):
        prompt = f"{prompt}\nImage: {question['image_keyword']}"
    if question.get("tokens"):
        prompt = f"{prompt}\nTokens: {' / '.join(question['tokens'])}"
    return prompt


def _external_mobile_content(lesson: dict[str, Any]) -> dict[str, Any]:
    raw = lesson.get("content", {})
    lesson_type = lesson.get("lesson_type", "")
    level = int(lesson["hsk_level"])
    title = lesson.get("title", "")
    content: dict[str, Any] = {
        "source_id": lesson.get("id"),
        "hsk_level": level,
        "category": title.split(": ", 1)[-1] or TYPE_TITLES.get(lesson_type, lesson_type.title()),
        "learning_objectives": lesson.get("learning_objectives", []),
    }

    focus = raw.get("focus")
    if focus:
        content["overview"] = focus
        content["overview_translations"] = _translations(focus, raw.get("focus_vi") or focus)

    vocabulary = _external_vocabulary_entries(lesson)
    grammar_points = _external_grammar_points(lesson)
    if vocabulary:
        content["vocabulary"] = vocabulary
    if grammar_points:
        content["grammar_points"] = grammar_points
        content["sentence_patterns"] = [
            _sentence_pattern_from_grammar(point)
            for point in grammar_points
            if point.get("structure")
        ]

    text_entry = _external_text_entry(raw)
    if text_entry and lesson_type == "reading":
        content["reading"] = {
            "title": title,
            "title_translations": _translations(title, title),
            "chinese": text_entry["hanzi"],
            "pinyin": text_entry.get("pinyin", ""),
            "vietnamese": text_entry.get("meaning", ""),
            "english": raw.get("english", ""),
            "translations": _translations(raw.get("english", ""), raw.get("vietnamese", text_entry.get("meaning", ""))),
        }
    elif text_entry and lesson_type == "listening":
        content["listening"] = {
            "script": text_entry["hanzi"],
            "pinyin": text_entry.get("pinyin", ""),
            "vietnamese": text_entry.get("meaning", ""),
            "english": raw.get("english", ""),
            "translations": _translations(raw.get("english", ""), raw.get("vietnamese", text_entry.get("meaning", ""))),
            "task": focus or "Listen and answer the checkpoint.",
            "task_translations": _translations(focus or "Listen and answer the checkpoint.", focus or "Nghe và trả lời câu kiểm tra."),
        }
        content["transcript"] = [text_entry]
    elif text_entry and lesson_type == "conversation":
        content["dialogue"] = {
            "title": title,
            "title_translations": _translations(title, title),
            "lines": [
                {
                    "speaker": "A",
                    "chinese": text_entry["hanzi"],
                    "pinyin": text_entry.get("pinyin", ""),
                    "vietnamese": text_entry.get("meaning", ""),
                    "english": raw.get("english", ""),
                    "translations": _translations(raw.get("english", ""), text_entry.get("meaning", "")),
                }
            ],
        }
    elif text_entry:
        content["passage_title"] = title
        content["passage_title_translations"] = _translations(title, title)
        content["passage"] = [text_entry]

    items = raw.get("items", [])
    item_texts = [item.get("text", "") for item in items if isinstance(item, dict) and item.get("text")]
    item_types = {item.get("type") for item in items if isinstance(item, dict)}
    if "pattern" in item_types:
        content["sentence_patterns"] = content.get("sentence_patterns", []) + [
            {
                "pattern": text,
                "meaning_vi": focus or "",
                "meaning_en": focus or "",
                "translations": _translations(focus or "", focus or ""),
            }
            for text in item_texts
        ]
    elif "activity" in item_types:
        content["speaking_tasks"] = item_texts
        content["speaking_task_translations"] = {"en": item_texts, "vi": item_texts}
    elif "review_scope" in item_types:
        content["reading_tasks"] = item_texts
        content["reading_task_translations"] = {"en": item_texts, "vi": item_texts}
    elif item_texts:
        content["reading_tasks"] = item_texts
        content["reading_task_translations"] = {"en": item_texts, "vi": item_texts}

    cultural_note = raw.get("cultural_note", {})
    if isinstance(cultural_note, dict) and (cultural_note.get("english") or cultural_note.get("vietnamese")):
        content["cultural_note"] = cultural_note

    return content


def _external_content_lessons() -> list[dict[str, Any]]:
    lessons = []
    for filename in ("hsk_curriculum_complete.json", "conversation_lessons.json", "conversation_quizzes.json"):
        path = CONTENT_DIR / filename
        if not path.exists():
            continue
        data = _load_json(path)
        source_lessons = data.get("levels", []) if isinstance(data, dict) else data
        if isinstance(data, dict):
            items = [
                lesson
                for level in source_lessons
                for lesson in level.get("lessons", [])
            ]
        else:
            items = source_lessons

        for lesson in items:
            source_id = lesson.get("id")
            if not source_id:
                continue
            questions = [
                {
                    "type": question.get("type", "multiple_choice"),
                    "prompt": _external_question_prompt(question),
                    "options": question.get("options", []),
                    "correct_answer": question.get("correct_answer", ""),
                    "explanation": question.get("explanation", ""),
                }
                for question in lesson.get("content", {}).get("questions", [])
            ]
            lessons.append(
                {
                    "id": source_id,
                    "hsk_level": int(lesson["hsk_level"]),
                    "title": lesson.get("title", source_id),
                    "description": (lesson.get("learning_objectives") or [lesson.get("content", {}).get("focus") or None])[0],
                    "lesson_type": lesson.get("lesson_type", "mixed"),
                    "sort_order": SORT_OFFSETS.get(filename, 0) + int(lesson.get("order", 0)),
                    "duration_minutes": int(lesson.get("estimated_duration_minutes", 10)),
                    "content": _external_mobile_content(lesson),
                    "questions": questions,
                }
            )
    return lessons


def _hsk1_reading_lessons() -> list[dict[str, Any]]:
    path = CONTENT_DIR / "hsk1_reading_passages.json"
    if not path.exists():
        return []

    lessons = []
    for index, passage in enumerate(_load_json(path), start=1):
        source_id = f"HSK1-READING-PASSAGE-{index:03d}"
        answer_key = passage.get("answer_key", {})
        questions = []
        reading_questions = []
        for question_index, question in enumerate(passage.get("comprehension_questions", []), start=1):
            question_id = question.get("id", f"q{question_index}")
            answer = answer_key.get(question_id, "")
            questions.append(
                {
                    "type": "multiple_choice",
                    "prompt": question.get("question", ""),
                    "options": question.get("options", []),
                    "correct_answer": answer,
                    "explanation": passage.get("explanation", ""),
                }
            )
            reading_questions.append(
                {
                    "question": question.get("question", ""),
                    "answer": answer,
                    "explanation": passage.get("explanation", ""),
                }
            )

        vocabulary_list = passage.get("vocabulary_list", [])
        first_question = questions[0] if questions else None
        first_keyword = vocabulary_list[0] if vocabulary_list else passage.get("chinese_text", "")[:1]
        lessons.append(
            {
                "id": source_id,
                "hsk_level": _hsk_level_number(passage.get("hsk_level", "HSK1")),
                "title": f"HSK1 Reading: {passage.get('title', f'Passage {index:03d}').split(': ', 1)[-1]}",
                "description": "Read a short HSK1 passage and answer comprehension questions.",
                "lesson_type": "reading",
                "sort_order": 7000 + index,
                "duration_minutes": 10,
                "content": {
                    "source_id": source_id,
                    "category": "Reading Passages",
                    "learning_objectives": [
                        "Read a short HSK1 text with familiar words.",
                        "Answer simple comprehension questions.",
                    ],
                    "vocabulary": [
                        _chinese_entry(word)
                        for word in passage.get("vocabulary_list", [])
                    ],
                    "passage_title": passage.get("title", ""),
                    "passage": [
                        _chinese_entry(
                            passage.get("chinese_text", ""),
                            passage.get("pinyin", ""),
                            _meaning(passage.get("english_translation"), passage.get("vietnamese_translation")),
                        )
                    ],
                    "reading": {
                        "title": passage.get("title", ""),
                        "chinese": passage.get("chinese_text", ""),
                        "pinyin": passage.get("pinyin", ""),
                        "english": passage.get("english_translation", ""),
                        "vietnamese": passage.get("vietnamese_translation", ""),
                        "questions": reading_questions,
                    },
                    "practice_exercises": [
                        {
                            "id": f"{source_id}-PRACTICE-QUESTION",
                            "title": "Reading checkpoint",
                            "exercise_type": "multiple_choice",
                            "skill": "reading",
                            "prompt": first_question["prompt"] if first_question else "What is the passage about?",
                            "options": first_question["options"] if first_question else ["Reading", "Listening", "Writing", "Grammar"],
                            "correct_answer": first_question["correct_answer"] if first_question else "Reading",
                            "hint": "Đọc lại câu chứa thông tin chính trong đoạn.",
                            "explanation": passage.get("explanation", ""),
                        },
                        {
                            "id": f"{source_id}-PRACTICE-KEYWORD",
                            "title": "Keyword recall",
                            "exercise_type": "text_input",
                            "skill": "reading",
                            "prompt": "Nhập một từ/cụm xuất hiện trong bài đọc.",
                            "correct_answer": first_keyword,
                            "expected_answer": first_keyword,
                            "hint": "Xem lại danh sách từ vựng của passage.",
                            "explanation": f"{first_keyword} xuất hiện trong đoạn đọc này.",
                        },
                    ],
                },
                "questions": questions,
            }
        )
    return lessons


def _pick_items(items: list[Any], start: int, count: int) -> list[Any]:
    return [items[(start + offset) % len(items)] for offset in range(count)]


def _word_entry(word: tuple[str, str, str, str], level: int, topic: dict[str, str]) -> dict[str, Any]:
    hanzi, pinyin, meaning_vi, meaning_en = word
    return {
        "hanzi": hanzi,
        "pinyin": pinyin,
        "meaning": meaning_vi,
        "meaning_vi": meaning_vi,
        "meaning_en": meaning_en,
        "translations": _translations(meaning_en, meaning_vi),
        "word_type": _word_type(hanzi),
        "category": topic["title"],
        "hsk_level": level,
        "example_cn": f"今天我练习{hanzi}。",
        "example_pinyin": f"Jin1tian1 wo3 lian4xi2 {pinyin}.",
        "example_vi": f"Hôm nay tôi luyện từ/cụm \"{meaning_vi}\".",
        "example_en": f"Today I practice \"{meaning_en}\".",
        "example_translations": _translations(
            f"Today I practice \"{meaning_en}\".",
            f"Hôm nay tôi luyện từ/cụm \"{meaning_vi}\".",
        ),
        "usage_note": f"Từ trọng tâm HSK {level} cho chủ đề {topic['vi']}.",
        "usage_note_translations": _translations(
            f"Core HSK {level} word for the topic {topic['title'].lower()}.",
            f"Từ trọng tâm HSK {level} cho chủ đề {topic['vi']}.",
        ),
    }


def _word_type(hanzi: str) -> str:
    if hanzi in PRONOUN_WORDS:
        return "pronoun"
    if hanzi in TIME_WORDS:
        return "time expression"
    if hanzi in CONNECTOR_WORDS:
        return "conjunction"
    if hanzi in PLACE_WORDS:
        return "place noun"
    if hanzi in VERB_WORDS:
        return "verb"
    if hanzi in ADJECTIVE_WORDS:
        return "adjective"
    return "noun"


def _with_correct_option(correct: str, candidates: list[str]) -> list[str]:
    options = [correct]
    for candidate in candidates:
        if candidate and candidate not in options:
            options.append(candidate)
        if len(options) == 4:
            break
    fallback_options = ["ôn tập", "luyện nghe", "đọc hiểu", "viết câu"]
    for fallback in fallback_options:
        if len(options) == 4:
            break
        if fallback not in options:
            options.append(fallback)
    return options


def _grammar_point(level: int, lesson_number: int) -> dict[str, Any]:
    title, structure, explanation, example_cn, example_pinyin, example_vi = GRAMMAR_PATTERNS[level][
        lesson_number - 1
    ]
    explanation_en = (
        f"Use the pattern {structure} to build accurate HSK {level} sentences. "
        "Read the example aloud, then replace one key word."
    )
    return {
        "title": title,
        "title_translations": _translations(title, title),
        "structure": structure,
        "explanation": explanation,
        "explanation_translations": _translations(explanation_en, explanation),
        "examples": [
            {
                **_chinese_entry(example_cn, example_pinyin, example_vi),
                "meaning_vi": example_vi,
                "meaning_en": "Study the grammar example and reuse the pattern.",
                "translations": _translations(
                    "Study the grammar example and reuse the pattern.",
                    example_vi,
                ),
            },
        ],
        "common_mistakes": [
            "Không dịch từng từ theo tiếng Việt; hãy giữ đúng trật tự của mẫu.",
            "Đọc to ví dụ rồi thay một từ vựng mới trước khi làm quiz.",
        ],
        "common_mistakes_translations": {
            "en": [
                "Do not translate word for word; keep the pattern order.",
                "Read the example aloud, then replace one vocabulary item before the quiz.",
            ],
            "vi": [
                "Không dịch từng từ theo tiếng Việt; hãy giữ đúng trật tự của mẫu.",
                "Đọc to ví dụ rồi thay một từ vựng mới trước khi làm quiz.",
            ],
        },
    }


def _sentence_pattern_from_grammar(point: dict[str, Any]) -> dict[str, Any]:
    examples = point.get("examples") or []
    example_text = examples[0]["hanzi"] if examples else ""
    return {
        "pattern": point["structure"],
        "meaning_vi": point["explanation"],
        "meaning_en": point.get("explanation_translations", {}).get("en", point["explanation"]),
        "translations": _translations(
            point.get("explanation_translations", {}).get("en", point["explanation"]),
            point["explanation"],
        ),
        "examples": [example_text] if example_text else [],
    }


def _dialogue_content(topic: dict[str, str], vocabulary: list[dict[str, Any]]) -> dict[str, Any]:
    w0, w1, w2 = vocabulary[0], vocabulary[1], vocabulary[2]
    first_vi = f"Hôm nay chúng ta luyện {w0['meaning']}, được không?"
    first_en = f"Today we practice {w0.get('meaning_en', w0['meaning'])}. Is that okay?"
    second_vi = f"Được. Tôi muốn dùng {w1['meaning']} và {w2['meaning']} để nói một câu."
    second_en = (
        f"Yes. I want to use {w1.get('meaning_en', w1['meaning'])} "
        f"and {w2.get('meaning_en', w2['meaning'])} to say one sentence."
    )
    return {
        "title": f"{topic['title']} Dialogue",
        "title_translations": _translations(
            f"{topic['title']} Dialogue",
            f"Hội thoại: {topic['vi']}",
        ),
        "lines": [
            {
                "speaker": "A",
                "chinese": f"今天我们练习{w0['hanzi']}，可以吗？",
                "pinyin": f"Jin1tian1 wo3men5 lian4xi2 {w0.get('pinyin', '')}, ke3yi3 ma5?",
                "vietnamese": first_vi,
                "english": first_en,
                "translations": _translations(first_en, first_vi),
            },
            {
                "speaker": "B",
                "chinese": f"可以。我想用{w1['hanzi']}和{w2['hanzi']}说一句话。",
                "pinyin": f"Ke3yi3. Wo3 xiang3 yong4 {w1.get('pinyin', '')} he2 {w2.get('pinyin', '')} shuo1 yi2 ju4 hua4.",
                "vietnamese": second_vi,
                "english": second_en,
                "translations": _translations(second_en, second_vi),
            },
        ],
        "vocabulary_list": [word["hanzi"] for word in vocabulary[:5]],
        "grammar_list": [],
        "cultural_note": "Trong luyện nói HSK, câu ngắn nhưng đúng trật tự quan trọng hơn câu dài.",
        "cultural_note_translations": _translations(
            "In HSK speaking practice, a short sentence with correct order matters more than a long sentence.",
            "Trong luyện nói HSK, câu ngắn nhưng đúng trật tự quan trọng hơn câu dài.",
        ),
    }


def _reading_content(level: int, topic: dict[str, str], vocabulary: list[dict[str, Any]]) -> dict[str, Any]:
    w0, w1, w2, w3 = vocabulary[:4]
    if level <= 2:
        chinese = (
            f"今天的主题是{w0['hanzi']}。学生先听老师说。然后大家一起读课文。"
            f"最后，学生用{w1['hanzi']}、{w2['hanzi']}和{w3['hanzi']}回答问题。这样学习更容易记住。"
        )
        vietnamese = (
            f"Chủ đề hôm nay là {topic['vi']}. Học viên nghe giáo viên trước, sau đó cùng đọc bài. "
            f"Cuối cùng họ dùng {w1['meaning']}, {w2['meaning']} và {w3['meaning']} để trả lời. "
            "Cách học này giúp dễ nhớ hơn."
        )
    elif level <= 4:
        chinese = (
            f"为了提高{w0['hanzi']}方面的能力，学生先整理关键词，再阅读一段短文。"
            f"他们把{w1['hanzi']}、{w2['hanzi']}和{w3['hanzi']}写在笔记里，"
            "然后用自己的话解释主要内容。虽然过程有点难，但是复习以后会更清楚。"
        )
        vietnamese = (
            f"Để cải thiện năng lực về {topic['vi']}, học viên sắp xếp từ khóa rồi đọc một đoạn ngắn. "
            f"Họ ghi {w1['meaning']}, {w2['meaning']} và {w3['meaning']} vào vở, "
            "sau đó giải thích nội dung chính bằng lời của mình. Tuy hơi khó, ôn lại sẽ rõ hơn."
        )
    else:
        chinese = (
            f"从长期学习来看，{w0['hanzi']}不仅是词汇主题，也是组织表达的线索。"
            f"学习者需要观察{w1['hanzi']}与{w2['hanzi']}之间的关系，"
            f"再用{w3['hanzi']}说明自己的判断。由此可见，高级阅读更强调信息整合和观点表达。"
        )
        vietnamese = (
            f"Nhìn từ việc học dài hạn, {topic['vi']} không chỉ là chủ đề từ vựng mà còn là mạch tổ chức diễn đạt. "
            f"Người học cần quan sát quan hệ giữa {w1['meaning']} và {w2['meaning']}, "
            f"sau đó dùng {w3['meaning']} để trình bày phán đoán. Vì vậy đọc nâng cao nhấn mạnh tổng hợp thông tin và bày tỏ quan điểm."
        )
    english = (
        f"Today's theme is {topic['title'].lower()}. Learners listen first, read next, "
        "and then answer with the key vocabulary."
    )
    return {
        "title": f"Short Reading: {topic['title']}",
        "title_translations": _translations(
            f"Short Reading: {topic['title']}",
            f"Bài đọc ngắn: {topic['vi']}",
        ),
        "chinese": chinese,
        "pinyin": "",
        "vietnamese": vietnamese,
        "english": english,
        "translations": _translations(english, vietnamese),
        "questions": [
            {
                "question": "Người học làm gì trước?",
                "question_translations": _translations(
                    "What does the learner do first?",
                    "Người học làm gì trước?",
                ),
                "answer": "先听老师说",
                "answer_translations": _translations("Listen to the teacher first.", "先听老师说"),
                "explanation": "Bài đọc nói 学生先听老师说.",
                "explanation_translations": _translations(
                    "The passage says 学生先听老师说.",
                    "Bài đọc nói 学生先听老师说.",
                ),
            },
            {
                "question": "Mục tiêu của cách học này là gì?",
                "question_translations": _translations(
                    "What is the goal of this study method?",
                    "Mục tiêu của cách học này là gì?",
                ),
                "answer": "内容更清楚，也更容易记住",
                "answer_translations": _translations(
                    "The content becomes clearer and easier to remember.",
                    "内容更清楚，也更容易记住",
                ),
                "explanation": "Câu cuối nêu rõ lợi ích của quy trình nghe, đọc, trả lời.",
                "explanation_translations": _translations(
                    "The final sentence explains the benefit of listening, reading, and answering.",
                    "Câu cuối nêu rõ lợi ích của quy trình nghe, đọc, trả lời.",
                ),
            },
        ],
    }


def _practice_exercises(
    level: int,
    lesson_number: int,
    lesson_type: str,
    topic: dict[str, str],
    vocabulary: list[dict[str, Any]],
    grammar_point: dict[str, Any],
    listening: dict[str, Any],
) -> list[dict[str, Any]]:
    w0, w1, w2 = vocabulary[:3]
    grammar_example = (grammar_point.get("examples") or [{}])[0]
    exercise_prefix = f"HSK{level}-{lesson_type.upper()}-{lesson_number:03d}"
    meanings = [item[2] for item in LEVEL_WORDS[level]]

    exercises: list[dict[str, Any]] = [
        {
            "id": f"{exercise_prefix}-VOCAB",
            "title": "Vocabulary recall",
            "title_translations": _translations("Vocabulary recall", "Nhớ nghĩa từ vựng"),
            "exercise_type": "multiple_choice",
            "skill": "vocabulary",
            "prompt": f"{w0['hanzi']} nghĩa là gì?",
            "prompt_translations": _translations(
                f"What does {w0['hanzi']} mean?",
                f"{w0['hanzi']} nghĩa là gì?",
            ),
            "options": _with_correct_option(str(w0["meaning"]), meanings),
            "correct_answer": str(w0["meaning"]),
            "hint": f"Pinyin: {w0.get('pinyin', '')}",
            "hint_translations": _translations(
                f"Pinyin: {w0.get('pinyin', '')}",
                f"Pinyin: {w0.get('pinyin', '')}",
            ),
            "explanation": f"{w0['hanzi']} là từ HSK {level}, nghĩa là {w0['meaning']}.",
            "explanation_translations": _translations(
                f"{w0['hanzi']} is an HSK {level} word meaning {w0.get('meaning_en', w0['meaning'])}.",
                f"{w0['hanzi']} là từ HSK {level}, nghĩa là {w0['meaning']}.",
            ),
        },
        {
            "id": f"{exercise_prefix}-GRAMMAR",
            "title": "Grammar pattern",
            "title_translations": _translations("Grammar pattern", "Mẫu ngữ pháp"),
            "exercise_type": "text_input",
            "skill": "grammar",
            "prompt": f"Gõ lại câu mẫu cho mẫu ngữ pháp: {grammar_point['structure']}",
            "prompt_translations": _translations(
                f"Type the example sentence for this grammar pattern: {grammar_point['structure']}",
                f"Gõ lại câu mẫu cho mẫu ngữ pháp: {grammar_point['structure']}",
            ),
            "correct_answer": str(grammar_example.get("hanzi", "")),
            "expected_answer": str(grammar_example.get("hanzi", "")),
            "hint": str(grammar_example.get("pinyin", "")),
            "hint_translations": _translations(str(grammar_example.get("pinyin", "")), str(grammar_example.get("pinyin", ""))),
            "explanation": str(grammar_point["explanation"]),
            "explanation_translations": grammar_point.get("explanation_translations", _translations(None, str(grammar_point["explanation"]))),
        },
        {
            "id": f"{exercise_prefix}-KEYWORD",
            "title": "Key word in context",
            "title_translations": _translations("Key word in context", "Từ khóa trong ngữ cảnh"),
            "exercise_type": "fill_blank",
            "skill": lesson_type if lesson_type != "mixed" else "core",
            "prompt": f"Điền từ còn thiếu: 今天我们学习____。",
            "prompt_translations": _translations(
                "Fill in the missing word: 今天我们学习____。",
                "Điền từ còn thiếu: 今天我们学习____。",
            ),
            "correct_answer": str(w1["hanzi"]),
            "expected_answer": str(w1["hanzi"]),
            "hint": f"Nghĩa: {w1['meaning']} ({w1.get('pinyin', '')})",
            "hint_translations": _translations(
                f"Meaning: {w1.get('meaning_en', w1['meaning'])} ({w1.get('pinyin', '')})",
                f"Nghĩa: {w1['meaning']} ({w1.get('pinyin', '')})",
            ),
            "explanation": f"Câu đầy đủ: 今天我们学习{w1['hanzi']}。",
            "explanation_translations": _translations(
                f"Full sentence: 今天我们学习{w1['hanzi']}。",
                f"Câu đầy đủ: 今天我们学习{w1['hanzi']}。",
            ),
        },
    ]

    if lesson_type in {"listening", "mixed"}:
        exercises.append(
            {
                "id": f"{exercise_prefix}-LISTENING",
                "title": "Listening checkpoint",
                "title_translations": _translations("Listening checkpoint", "Kiểm tra nghe"),
                "exercise_type": "text_input",
                "skill": "listening",
                "prompt": "Nghe đoạn đọc và nhập từ khóa thứ hai bạn nghe được.",
                "prompt_translations": _translations(
                    "Listen to the script and type the second key word you hear.",
                    "Nghe đoạn đọc và nhập từ khóa thứ hai bạn nghe được.",
                ),
                "correct_answer": str(w1["hanzi"]),
                "expected_answer": str(w1["hanzi"]),
                "hint": listening.get("answer", ""),
                "hint_translations": _translations(listening.get("answer", ""), listening.get("answer", "")),
                "explanation": f"Trong script có cụm: {listening['script']}",
                "explanation_translations": _translations(
                    f"The script includes: {listening['script']}",
                    f"Trong script có cụm: {listening['script']}",
                ),
            }
        )

    if lesson_type in {"reading", "mixed"}:
        reading_answer = "先听老师说" if level <= 2 else "整理关键词" if level <= 4 else "观察关系"
        exercises.append(
            {
                "id": f"{exercise_prefix}-READING",
                "title": "Reading checkpoint",
                "title_translations": _translations("Reading checkpoint", "Kiểm tra đọc"),
                "exercise_type": "text_input",
                "skill": "reading",
                "prompt": "Theo bài đọc, người học làm gì trước?",
                "prompt_translations": _translations(
                    "According to the reading, what does the learner do first?",
                    "Theo bài đọc, người học làm gì trước?",
                ),
                "correct_answer": reading_answer,
                "expected_answer": reading_answer,
                "hint": "Tìm câu có chữ 先 hoặc cụm trình tự đầu tiên.",
                "hint_translations": _translations(
                    "Find the sentence with 先 or the first sequence phrase.",
                    "Tìm câu có chữ 先 hoặc cụm trình tự đầu tiên.",
                ),
                "explanation": "Bài đọc luôn nêu bước đầu tiên trước khi chuyển sang đọc hoặc giải thích.",
                "explanation_translations": _translations(
                    "The reading states the first step before moving to reading or explaining.",
                    "Bài đọc luôn nêu bước đầu tiên trước khi chuyển sang đọc hoặc giải thích.",
                ),
            }
        )

    return exercises


def _writing_exercises(
    level: int,
    lesson_number: int,
    lesson_type: str,
    vocabulary: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    w0, w1 = vocabulary[:2]
    exercise_prefix = f"HSK{level}-{lesson_type.upper()}-{lesson_number:03d}"
    sentence = f"我想学习{w1['hanzi']}"
    return [
        {
            "id": f"{exercise_prefix}-WRITE-CHAR",
            "title": "Character recall",
            "title_translations": _translations("Character recall", "Nhớ chữ Hán"),
            "exercise_type": "text_input",
            "skill": "writing",
            "prompt": f"Nhập chữ Hán cho nghĩa: {w0['meaning']}",
            "prompt_translations": _translations(
                f"Type the Chinese character for: {w0.get('meaning_en', w0['meaning'])}",
                f"Nhập chữ Hán cho nghĩa: {w0['meaning']}",
            ),
            "correct_answer": str(w0["hanzi"]),
            "expected_answer": str(w0["hanzi"]),
            "hint": f"Pinyin: {w0.get('pinyin', '')}",
            "hint_translations": _translations(f"Pinyin: {w0.get('pinyin', '')}", f"Pinyin: {w0.get('pinyin', '')}"),
            "explanation": f"Chữ cần viết là {w0['hanzi']}.",
            "explanation_translations": _translations(
                f"The character to write is {w0['hanzi']}.",
                f"Chữ cần viết là {w0['hanzi']}.",
            ),
        },
        {
            "id": f"{exercise_prefix}-WRITE-BLANK",
            "title": "Sentence completion",
            "title_translations": _translations("Sentence completion", "Hoàn thành câu"),
            "exercise_type": "fill_blank",
            "skill": "writing",
            "prompt": "Hoàn thành câu: 我想学习____。",
            "prompt_translations": _translations(
                "Complete the sentence: 我想学习____。",
                "Hoàn thành câu: 我想学习____。",
            ),
            "correct_answer": str(w1["hanzi"]),
            "expected_answer": str(w1["hanzi"]),
            "hint": f"Nghĩa cần điền: {w1['meaning']}",
            "hint_translations": _translations(
                f"Meaning to fill in: {w1.get('meaning_en', w1['meaning'])}",
                f"Nghĩa cần điền: {w1['meaning']}",
            ),
            "explanation": f"Câu đầy đủ: 我想学习{w1['hanzi']}。",
            "explanation_translations": _translations(
                f"Full sentence: 我想学习{w1['hanzi']}。",
                f"Câu đầy đủ: 我想学习{w1['hanzi']}。",
            ),
        },
        {
            "id": f"{exercise_prefix}-WRITE-ORDER",
            "title": "Sentence order",
            "title_translations": _translations("Sentence order", "Sắp xếp câu"),
            "exercise_type": "rearrange",
            "skill": "writing",
            "prompt": "Sắp xếp thành câu đúng rồi nhập lại.",
            "prompt_translations": _translations(
                "Put the words in the correct order and type the sentence.",
                "Sắp xếp thành câu đúng rồi nhập lại.",
            ),
            "word_bank": ["我", "想", "学习", str(w1["hanzi"])],
            "correct_answer": sentence,
            "expected_answer": sentence,
            "hint": "Trật tự cơ bản: chủ ngữ + muốn + động từ + tân ngữ.",
            "hint_translations": _translations(
                "Basic order: subject + want + verb + object.",
                "Trật tự cơ bản: chủ ngữ + muốn + động từ + tân ngữ.",
            ),
            "explanation": f"Câu đúng là: {sentence}。",
            "explanation_translations": _translations(
                f"The correct sentence is: {sentence}。",
                f"Câu đúng là: {sentence}。",
            ),
        },
    ]


def _listening_content(topic: dict[str, str], vocabulary: list[dict[str, Any]]) -> dict[str, Any]:
    w0, w1, w2 = vocabulary[:3]
    vietnamese = f"Hãy nghe. Hôm nay chúng ta học {topic['vi']}. Hãy dùng hai từ khóa để trả lời câu hỏi."
    english = f"Listen. Today we study {topic['title'].lower()}. Use two key words to answer the question."
    task_vi = "Nghe một lần để lấy ý chính, nghe lần hai để ghi lại hai từ khóa."
    task_en = "Listen once for the main idea, then listen again and write down two key words."
    return {
        "script": f"请听。今天我们学习{w0['hanzi']}。请用{w1['hanzi']}和{w2['hanzi']}回答问题。",
        "pinyin": f"Qing3 ting1. Jin1tian1 wo3men5 xue2xi2 {w0.get('pinyin', '')}. Qing3 yong4 {w1.get('pinyin', '')} he2 {w2.get('pinyin', '')} hui2da2 wen4ti2.",
        "vietnamese": vietnamese,
        "english": english,
        "translations": _translations(english, vietnamese),
        "task": task_vi,
        "task_translations": _translations(task_en, task_vi),
        "answer": f"{w1['hanzi']} / {w2['hanzi']}",
    }


def _writing_characters(vocabulary: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "hanzi": word["hanzi"],
            "pinyin": word.get("pinyin", ""),
            "meaning": word.get("meaning", ""),
            "meaning_vi": word.get("meaning_vi", word.get("meaning", "")),
            "meaning_en": word.get("meaning_en", ""),
            "translations": word.get("translations", {}),
        }
        for word in vocabulary[:6]
    ]


def _practice_tasks(topic: dict[str, str], vocabulary: list[dict[str, Any]]) -> dict[str, Any]:
    keywords = "、".join(word["hanzi"] for word in vocabulary[:4])
    return {
        "speaking_tasks": [
            f"Nói 3 câu ngắn về {topic['vi']} và dùng ít nhất hai từ: {keywords}.",
            "Ghi âm lại, nghe lại một lần, rồi sửa phát âm của một câu.",
        ],
        "speaking_task_translations": {
            "en": [
                f"Say 3 short sentences about {topic['title'].lower()} and use at least two words: {keywords}.",
                "Record yourself, listen once, then fix the pronunciation of one sentence.",
            ],
            "vi": [
                f"Nói 3 câu ngắn về {topic['vi']} và dùng ít nhất hai từ: {keywords}.",
                "Ghi âm lại, nghe lại một lần, rồi sửa phát âm của một câu.",
            ],
        },
        "reading_tasks": [
            "Gạch chân từ khóa trong bài đọc trước khi xem câu hỏi.",
            "Tóm tắt bài đọc bằng một câu tiếng Việt và một câu tiếng Trung.",
        ],
        "reading_task_translations": {
            "en": [
                "Underline key words in the reading before looking at the questions.",
                "Summarize the reading in one English sentence and one Chinese sentence.",
            ],
            "vi": [
                "Gạch chân từ khóa trong bài đọc trước khi xem câu hỏi.",
                "Tóm tắt bài đọc bằng một câu tiếng Việt và một câu tiếng Trung.",
            ],
        },
        "writing_tasks": [
            f"Viết 5 câu có dùng các từ {keywords}.",
            "Chọn một câu sai, viết lại cho ngắn và đúng trật tự hơn.",
        ],
        "writing_task_translations": {
            "en": [
                f"Write 5 sentences using these words: {keywords}.",
                "Choose one incorrect sentence and rewrite it shorter with better order.",
            ],
            "vi": [
                f"Viết 5 câu có dùng các từ {keywords}.",
                "Chọn một câu sai, viết lại cho ngắn và đúng trật tự hơn.",
            ],
        },
    }


def _generated_questions(
    level: int,
    lesson_number: int,
    lesson_type: str,
    topic: dict[str, str],
    vocabulary: list[dict[str, Any]],
    grammar_point: dict[str, Any],
) -> list[dict[str, Any]]:
    word = vocabulary[0]
    all_meanings = [item[2] for item in LEVEL_WORDS[level]]
    grammar_titles = [item[0] for item in GRAMMAR_PATTERNS[level]]
    topic_titles = [item["title"] for item in TOPICS]
    return [
        {
            "type": "multiple_choice",
            "prompt": f"{word['hanzi']} means...",
            "options": _with_correct_option(str(word["meaning"]), all_meanings),
            "correct_answer": str(word["meaning"]),
            "explanation": f"{word['hanzi']} ({word.get('pinyin', '')}) = {word['meaning']}.",
        },
        {
            "type": "multiple_choice",
            "prompt": f"Which grammar point is practiced in this {lesson_type} lesson?",
            "options": _with_correct_option(str(grammar_point["title"]), grammar_titles),
            "correct_answer": str(grammar_point["title"]),
            "explanation": f"The lesson highlights: {grammar_point['structure']}.",
        },
        {
            "type": "multiple_choice",
            "prompt": "What is the main topic of this lesson?",
            "options": _with_correct_option(topic["title"], topic_titles[lesson_number:] + topic_titles[:lesson_number]),
            "correct_answer": topic["title"],
            "explanation": f"The lesson title and tasks focus on {topic['title'].lower()}.",
        },
    ]


def _expanded_skill_lessons() -> list[dict[str, Any]]:
    lessons = []
    for level in range(1, 7):
        for lesson_type in GENERATED_LESSON_TYPES:
            for lesson_number, topic in enumerate(TOPICS[:GENERATED_LESSONS_PER_TYPE], start=1):
                vocabulary = [
                    _word_entry(word, level, topic)
                    for word in _pick_items(LEVEL_WORDS[level], (lesson_number - 1) * 3, 8)
                ]
                grammar_point = _grammar_point(level, lesson_number)
                reading = _reading_content(level, topic, vocabulary)
                listening = _listening_content(topic, vocabulary)
                practices = _practice_tasks(topic, vocabulary)
                source_id = f"HSK{level}-{lesson_type.upper()}-AUTO-{lesson_number:03d}"

                content: dict[str, Any] = {
                    "source_id": source_id,
                    "hsk_level": level,
                    "category": topic["title"],
                    "learning_objectives": [
                        f"Build HSK {level} language for {topic['vi']}.",
                        "Practice input, output, and quiz recall in one short session.",
                    ],
                    "learning_objective_translations": {
                        "en": [
                            f"Build HSK {level} language for {topic['title'].lower()}.",
                            "Practice input, output, and quiz recall in one short session.",
                        ],
                        "vi": [
                            f"Xây dựng ngôn ngữ HSK {level} cho chủ đề {topic['vi']}.",
                            "Luyện đầu vào, đầu ra và ghi nhớ qua quiz trong một buổi ngắn.",
                        ],
                    },
                    "overview": (
                        f"Focused {TYPE_TITLES[lesson_type].lower()} practice for HSK {level}. "
                        f"This unit uses the topic of {topic['vi']} with reusable vocabulary and tasks."
                    ),
                    "overview_translations": _translations(
                        (
                            f"Focused {TYPE_TITLES[lesson_type].lower()} practice for HSK {level}. "
                            f"This unit uses {topic['title'].lower()} with reusable vocabulary and tasks."
                        ),
                        (
                            f"Luyện {TYPE_TITLES[lesson_type].lower()} trọng tâm cho HSK {level}. "
                            f"Bài này dùng chủ đề {topic['vi']} với từ vựng và nhiệm vụ có thể tái sử dụng."
                        ),
                    ),
                    "vocabulary": vocabulary,
                }

                if lesson_type in {"mixed", "grammar"}:
                    content["grammar_points"] = [grammar_point]
                    content["sentence_patterns"] = [_sentence_pattern_from_grammar(grammar_point)]
                if lesson_type in {"mixed", "reading"}:
                    content["reading"] = reading
                if lesson_type in {"mixed", "listening"}:
                    content["listening"] = listening
                    content["transcript"] = [
                        _chinese_entry(listening["script"], listening.get("pinyin", ""), listening.get("vietnamese", ""))
                    ]
                if lesson_type in {"mixed", "writing"}:
                    content["characters"] = _writing_characters(vocabulary)
                    content["tip"] = "Viết chậm từng cụm, đọc to trước khi viết lại để kết nối âm và chữ."
                    content["tip_translations"] = _translations(
                        "Write slowly by phrase, read aloud before rewriting, and connect sound with character shape.",
                        "Viết chậm từng cụm, đọc to trước khi viết lại để kết nối âm và chữ.",
                    )
                    content["writing_exercises"] = _writing_exercises(level, lesson_number, lesson_type, vocabulary)
                if lesson_type == "mixed":
                    content["dialogue"] = _dialogue_content(topic, vocabulary)

                content.update(practices)
                content["practice_exercises"] = _practice_exercises(
                    level,
                    lesson_number,
                    lesson_type,
                    topic,
                    vocabulary,
                    grammar_point,
                    listening,
                )

                lessons.append(
                    {
                        "id": source_id,
                        "hsk_level": level,
                        "title": f"HSK{level} {TYPE_TITLES[lesson_type]} {lesson_number:02d}: {topic['title']}",
                        "description": (
                            f"{TYPE_TITLES[lesson_type]} practice for HSK {level}: {topic['title'].lower()}."
                        ),
                        "lesson_type": lesson_type,
                        "sort_order": TYPE_SORT_BASE[lesson_type] + lesson_number,
                        "duration_minutes": 12 if lesson_type in {"vocabulary", "writing"} else 15,
                        "content": content,
                        "questions": _generated_questions(
                            level,
                            lesson_number,
                            lesson_type,
                            topic,
                            vocabulary,
                            grammar_point,
                        ),
                    }
                )
    return lessons


def _content_lessons() -> list[dict[str, Any]]:
    return _rich_lessons() + _external_content_lessons() + _hsk1_reading_lessons() + _expanded_skill_lessons()


def _fallback_practice_exercises(
    source_id: str,
    lesson_type: str,
    questions: list[dict[str, Any]],
    content: dict[str, Any],
) -> list[dict[str, Any]]:
    exercises = []
    for index, question in enumerate(questions[:2], start=1):
        exercise_type = "multiple_choice" if question.get("options") else "text_input"
        exercises.append(
            {
                "id": f"{source_id}-FALLBACK-{index}",
                "title": f"{TYPE_TITLES.get(lesson_type, 'Lesson')} checkpoint",
                "exercise_type": exercise_type,
                "skill": lesson_type,
                "prompt": question.get("prompt", "Review the lesson and answer."),
                "options": question.get("options"),
                "correct_answer": question.get("correct_answer", ""),
                "expected_answer": question.get("correct_answer", ""),
                "hint": "Xem lại nội dung chính của bài trước khi trả lời.",
                "explanation": question.get("explanation", ""),
            }
        )

    if exercises:
        return exercises

    vocabulary = content.get("vocabulary") or content.get("characters") or []
    if not vocabulary:
        return []

    first_word = vocabulary[0]
    if not isinstance(first_word, dict):
        return []

    answer = str(first_word.get("hanzi", ""))
    if not answer:
        return []

    return [
        {
            "id": f"{source_id}-FALLBACK-KEYWORD",
            "title": f"{TYPE_TITLES.get(lesson_type, 'Lesson')} recall",
            "exercise_type": "text_input",
            "skill": lesson_type,
            "prompt": "Nhập lại từ khóa đầu tiên của bài.",
            "correct_answer": answer,
            "expected_answer": answer,
            "hint": str(first_word.get("pinyin", "")),
            "explanation": f"Từ khóa đầu tiên là {answer}.",
        }
    ]


def _augment_chinese_entry(entry: dict[str, Any]) -> None:
    if not entry.get("hanzi"):
        return

    meaning_vi = entry.get("meaning_vi") or entry.get("vietnamese") or entry.get("meaning")
    meaning_en = entry.get("meaning_en") or entry.get("english")
    if meaning_vi:
        entry.setdefault("meaning_vi", meaning_vi)
    if meaning_en:
        entry.setdefault("meaning_en", meaning_en)
    if meaning_en or meaning_vi:
        entry.setdefault("translations", _translations(meaning_en, meaning_vi))

    if entry.get("example_en") or entry.get("example_vi"):
        entry.setdefault("example_translations", _translations(entry.get("example_en"), entry.get("example_vi")))


def _augment_content_translations(content: dict[str, Any]) -> dict[str, Any]:
    overview = content.get("overview")
    if overview and "overview_translations" not in content:
        content["overview_translations"] = _translations(overview, overview)

    objectives = content.get("learning_objectives")
    if isinstance(objectives, list) and "learning_objective_translations" not in content:
        content["learning_objective_translations"] = {"en": objectives, "vi": objectives}

    for field in ("vocabulary", "characters", "passage", "transcript", "patterns"):
        for entry in content.get(field) or []:
            if isinstance(entry, dict):
                _augment_chinese_entry(entry)

    for point in content.get("grammar_points") or []:
        if not isinstance(point, dict):
            continue
        title = point.get("title")
        explanation = point.get("explanation")
        if title:
            point.setdefault("title_translations", _translations(title, title))
        if explanation:
            point.setdefault("explanation_translations", _translations(explanation, explanation))
        if point.get("common_mistakes") and "common_mistakes_translations" not in point:
            point["common_mistakes_translations"] = {
                "en": point["common_mistakes"],
                "vi": point["common_mistakes"],
            }
        for example in point.get("examples") or []:
            if isinstance(example, dict):
                _augment_chinese_entry(example)

    for pattern in content.get("sentence_patterns") or []:
        if not isinstance(pattern, dict):
            continue
        meaning_vi = pattern.get("meaning_vi")
        meaning_en = pattern.get("meaning_en")
        if meaning_en or meaning_vi:
            pattern.setdefault("translations", _translations(meaning_en, meaning_vi))

    reading = content.get("reading")
    if isinstance(reading, dict):
        if reading.get("title"):
            reading.setdefault("title_translations", _translations(reading.get("title"), reading.get("title")))
        if reading.get("english") or reading.get("vietnamese"):
            reading.setdefault("translations", _translations(reading.get("english"), reading.get("vietnamese")))
        for question in reading.get("questions") or []:
            if not isinstance(question, dict):
                continue
            if question.get("question"):
                question.setdefault("question_translations", _translations(question.get("question"), question.get("question")))
            if question.get("answer"):
                question.setdefault("answer_translations", _translations(question.get("answer"), question.get("answer")))
            if question.get("explanation"):
                question.setdefault(
                    "explanation_translations",
                    _translations(question.get("explanation"), question.get("explanation")),
                )

    listening = content.get("listening")
    if isinstance(listening, dict):
        if listening.get("english") or listening.get("vietnamese"):
            listening.setdefault("translations", _translations(listening.get("english"), listening.get("vietnamese")))
        if listening.get("task"):
            listening.setdefault("task_translations", _translations(listening.get("task"), listening.get("task")))
        if listening.get("answer"):
            listening.setdefault("answer_translations", _translations(listening.get("answer"), listening.get("answer")))

    dialogue = content.get("dialogue")
    if isinstance(dialogue, dict):
        if dialogue.get("title"):
            dialogue.setdefault("title_translations", _translations(dialogue.get("title"), dialogue.get("title")))
        for line in dialogue.get("lines") or []:
            if isinstance(line, dict) and (line.get("english") or line.get("vietnamese")):
                line.setdefault("translations", _translations(line.get("english"), line.get("vietnamese")))
        if dialogue.get("cultural_note"):
            dialogue.setdefault(
                "cultural_note_translations",
                _translations(dialogue.get("cultural_note"), dialogue.get("cultural_note")),
            )

    cultural_note = content.get("cultural_note")
    if isinstance(cultural_note, dict) and "translations" not in cultural_note:
        cultural_note["translations"] = _translations(cultural_note.get("english"), cultural_note.get("vietnamese"))

    for exercise_field in ("practice_exercises", "writing_exercises"):
        for exercise in content.get(exercise_field) or []:
            if not isinstance(exercise, dict):
                continue
            for base_field in ("title", "prompt", "hint", "explanation"):
                value = exercise.get(base_field)
                translations_key = f"{base_field}_translations"
                if value and translations_key not in exercise:
                    exercise[translations_key] = _translations(value, value)

    return content



def _ensure_levels(db: Session) -> dict[int, HskLevel]:
    levels = {level.level_number: level for level in db.scalars(select(HskLevel)).all()}
    for level_number in range(1, 7):
        if level_number not in levels:
            level = HskLevel(
                level_number=level_number,
                title=f"HSK {level_number}",
                description=f"Structured Mandarin lessons for HSK {level_number}.",
                total_characters=LEVEL_CHARACTER_TOTALS[level_number - 1],
            )
            db.add(level)
            levels[level_number] = level
    db.flush()
    return levels


def _upsert_content_lessons(db: Session, levels: dict[int, HskLevel]) -> None:
    existing_by_source_id = {
        lesson.content.get("source_id"): lesson
        for lesson in db.scalars(select(Lesson)).all()
        if isinstance(lesson.content, dict) and lesson.content.get("source_id")
    }

    for item in _content_lessons():
        source_id = item["id"]
        hsk_level = int(item["hsk_level"])
        lesson = existing_by_source_id.get(source_id)
        if lesson is None:
            lesson = Lesson(hsk_level_id=levels[hsk_level].id)
            db.add(lesson)
            existing_by_source_id[source_id] = lesson

        content = _augment_content_translations(dict(item["content"]))
        content["source_id"] = source_id
        content["hsk_level"] = hsk_level
        content.setdefault("category", TYPE_TITLES.get(item["lesson_type"], item["lesson_type"].title()))
        if not content.get("practice_exercises"):
            content["practice_exercises"] = _fallback_practice_exercises(
                source_id,
                item["lesson_type"],
                item.get("questions", []),
                content,
            )
        lesson.hsk_level_id = levels[hsk_level].id
        lesson.title = item["title"]
        lesson.description = item.get("description")
        lesson.lesson_type = item["lesson_type"]
        lesson.sort_order = int(item["sort_order"])
        lesson.duration_minutes = int(item["duration_minutes"])
        lesson.content = content
        db.flush()

        existing_questions = {
            question.sort_order: question
            for question in db.scalars(select(Question).where(Question.lesson_id == lesson.id)).all()
        }
        for index, question_data in enumerate(item.get("questions", []), start=1):
            question = existing_questions.get(index)
            if question is None:
                question = Question(lesson_id=lesson.id, sort_order=index)
                db.add(question)
            question.question_type = question_data.get("type", "multiple_choice")
            question.prompt = question_data.get("prompt", "")
            question.options = question_data.get("options") or None
            question.correct_answer = question_data.get("correct_answer", "")
            question.explanation = question_data.get("explanation", "")
        for sort_order, question in existing_questions.items():
            if sort_order > len(item.get("questions", [])):
                db.delete(question)


def _upsert_achievements(db: Session) -> None:
    existing = {achievement.code: achievement for achievement in db.scalars(select(Achievement)).all()}
    for item in ACHIEVEMENTS:
        achievement = existing.get(item["code"])
        if achievement is None:
            achievement = Achievement(code=item["code"])
            db.add(achievement)
        achievement.title = item["title"]
        achievement.description = item["description"]
        achievement.icon = item["icon"]


def _upsert_mock_tests(db: Session) -> None:
    existing = {mock_test.title: mock_test for mock_test in db.scalars(select(MockTest)).all()}
    for item in MOCK_TESTS:
        mock_test = existing.get(item["title"])
        if mock_test is None:
            mock_test = MockTest(title=item["title"])
            db.add(mock_test)
        mock_test.hsk_level = item["hsk_level"]
        mock_test.duration_minutes = item["duration_minutes"]
        mock_test.question_count = item["question_count"]



def seed_data(db: Session) -> None:
    levels = _ensure_levels(db)
    _upsert_content_lessons(db, levels)
    _upsert_achievements(db)
    _upsert_mock_tests(db)
    db.commit()
