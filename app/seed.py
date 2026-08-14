import json
import re
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Achievement,
    ContentStatus,
    Course,
    HskLevel,
    Lesson,
    MockTest,
    Question,
)

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

TYPE_TITLES_VI = {
    "mixed": "Bài học cốt lõi",
    "vocabulary": "Từ vựng",
    "grammar": "Ngữ pháp",
    "listening": "Nghe",
    "reading": "Đọc hiểu",
    "sentence_pattern": "Mẫu câu",
    "conversation": "Hội thoại",
    "review": "Ôn tập",
    "practice": "Luyện tập",
    "quiz": "Quiz",
    "writing": "Viết",
}

TYPE_SORT_BASE = {
    "mixed": 1000,
    "vocabulary": 2000,
    "grammar": 3000,
    "listening": 4000,
    "reading": 5000,
    "writing": 6000,
}

COURSE_TYPE_ORDER = {
    "mixed": 1,
    "vocabulary": 2,
    "grammar": 3,
    "reading": 4,
    "listening": 5,
    "writing": 6,
    "sentence_pattern": 7,
    "conversation": 8,
    "practice": 9,
    "review": 10,
    "quiz": 11,
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

TOPIC_TITLE_VI = {topic["title"]: topic["vi"] for topic in TOPICS}

TITLE_PHRASE_VI = {
    "Greetings and Self Introduction": "Chào hỏi và tự giới thiệu",
    "Plans and Time": "Kế hoạch và thời gian",
    "Solving a Delivery Problem": "Giải quyết vấn đề giao hàng",
    "Community Problems and Suggestions": "Vấn đề cộng đồng và góp ý",
    "Online Learning Efficiency": "Hiệu quả học trực tuyến",
    "People and Pronouns": "Con người và đại từ",
    "Identity with Shi": "Nhận diện với 是",
    "A New Classmate": "Bạn cùng lớp mới",
    "Morning Greeting": "Chào buổi sáng",
    "Asking Names": "Hỏi tên",
    "Meeting a New Classmate": "Gặp bạn cùng lớp mới",
    "First Introductions": "Giới thiệu ban đầu",
    "Introduction Builder": "Luyện xây dựng câu giới thiệu",
    "Introduction Checkpoint": "Kiểm tra phần giới thiệu",
    "Daily Actions": "Hoạt động hằng ngày",
    "Completed Actions": "Hành động đã hoàn thành",
    "Weekend Library Plan": "Kế hoạch thư viện cuối tuần",
    "Phone Plan": "Lên kế hoạch qua điện thoại",
    "Simple Comparisons": "So sánh đơn giản",
    "Borrowing a Library Book": "Mượn sách thư viện",
    "Daily Life and Plans": "Đời sống hằng ngày và kế hoạch",
    "Weekend Planner": "Lập kế hoạch cuối tuần",
    "Daily Communication Checkpoint": "Kiểm tra giao tiếp hằng ngày",
    "Problems and Solutions": "Vấn đề và giải pháp",
    "Handling Objects with Ba": "Xử lý tân ngữ với 把",
    "Online Delivery Problem": "Vấn đề giao hàng trực tuyến",
    "Work Reminder": "Nhắc việc ở nơi làm việc",
    "Reasons and Conditions": "Lý do và điều kiện",
    "Changing a Delivery Address": "Đổi địa chỉ giao hàng",
    "Problems, Results, and Requests": "Vấn đề, kết quả và yêu cầu",
    "Service Problem Solver": "Giải quyết vấn đề dịch vụ",
    "Practical Problem Checkpoint": "Kiểm tra xử lý vấn đề thực tế",
    "City and Society": "Thành phố và xã hội",
    "Contrast and Addition": "Tương phản và bổ sung",
    "A Neighborhood Noise Issue": "Vấn đề tiếng ồn khu dân cư",
    "Health Advice at Work": "Lời khuyên sức khỏe ở nơi làm việc",
    "Change and Conditions": "Thay đổi và điều kiện",
    "Discussing Exercise Habits": "Thảo luận thói quen vận động",
    "Society, Health, and Connectors": "Xã hội, sức khỏe và liên từ",
    "Opinion Paragraph Builder": "Luyện viết đoạn nêu ý kiến",
    "Intermediate Opinion Checkpoint": "Kiểm tra nêu ý kiến trung cấp",
    "Media and Viewpoints": "Truyền thông và quan điểm",
    "Formal Reasoning Patterns": "Mẫu lập luận trang trọng",
    "Career Interview": "Phỏng vấn nghề nghiệp",
    "Correcting Misunderstandings": "Điều chỉnh hiểu lầm",
    "Debating Online Learning": "Tranh luận về học trực tuyến",
    "Media, Work, and Argument": "Truyền thông, công việc và lập luận",
    "Argument Response Workshop": "Luyện phản hồi lập luận",
    "Formal Argument Checkpoint": "Kiểm tra lập luận trang trọng",
    "Analysis and Trends": "Phân tích và xu hướng",
    "Discourse Transitions": "Chuyển ý trong diễn ngôn",
    "Interpreting an Aging Society": "Diễn giải xã hội già hóa",
    "Research Claim and Evidence": "Luận điểm nghiên cứu và bằng chứng",
    "Academic Framing": "Khung diễn đạt học thuật",
    "Interpreting a Social Trend": "Diễn giải xu hướng xã hội",
    "Advanced Discourse and Analysis": "Diễn ngôn và phân tích nâng cao",
    "Analytical Response Studio": "Luyện phản hồi phân tích",
    "Advanced Mastery Checkpoint": "Kiểm tra thành thạo nâng cao",
    "Introducing Family Members": "Giới thiệu thành viên gia đình",
    "Ordering Noodles at a Restaurant": "Gọi mì ở nhà hàng",
    "Asking About Class": "Hỏi về buổi học",
    "Making Weekend Plans": "Lập kế hoạch cuối tuần",
    "Talking About the Weather": "Nói về thời tiết",
    "Buying a Shirt": "Mua áo",
    "Checking in at the Airport": "Làm thủ tục ở sân bay",
    "Checking in at a Hotel": "Nhận phòng khách sạn",
    "Planning a Meeting": "Lên kế hoạch họp",
    "Seeing a Doctor": "Đi khám bác sĩ",
    "Asking for Directions While Traveling": "Hỏi đường khi đi du lịch",
    "Hello": "Xin chào",
    "The Teacher": "Giáo viên",
    "At School": "Ở trường",
    "My Family": "Gia đình tôi",
    "Dad and Mom": "Bố và mẹ",
    "A Friend": "Một người bạn",
    "This Book": "Cuốn sách này",
    "Water": "Nước",
    "Tea": "Trà",
    "Rice": "Cơm",
    "Apples": "Táo",
    "Buying Fruit": "Mua trái cây",
    "How Much": "Bao nhiêu tiền",
    "Hot Weather": "Thời tiết nóng",
    "Cold Weather": "Thời tiết lạnh",
    "Rain": "Trời mưa",
    "Today and Tomorrow": "Hôm nay và ngày mai",
    "Yesterday": "Hôm qua",
    "What Time": "Mấy giờ",
    "Morning": "Buổi sáng",
    "Noon Meal": "Bữa trưa",
    "Sleep": "Ngủ",
    "Reading a Book": "Đọc sách",
    "Studying Chinese": "Học tiếng Trung",
    "Writing Characters": "Viết chữ Hán",
    "Speaking": "Nói",
    "Listening": "Nghe",
    "Television": "Tivi",
    "Movie": "Phim",
    "Computer": "Máy tính",
    "Phone Call": "Gọi điện thoại",
    "Taxi": "Taxi",
    "Airplane": "Máy bay",
    "Hotel": "Khách sạn",
    "Hospital": "Bệnh viện",
    "Chair and Table": "Ghế và bàn",
    "In the Room": "Trong phòng",
    "Front and Back": "Phía trước và phía sau",
    "Going Home": "Về nhà",
    "Coming to School": "Đến trường",
    "Beijing": "Bắc Kinh",
    "China": "Trung Quốc",
    "Where Do You Live": "Bạn sống ở đâu",
    "Knowing a Friend": "Quen một người bạn",
    "Who Is She": "Cô ấy là ai",
    "What Is This": "Đây là gì",
    "Where Is School": "Trường ở đâu",
    "Which Student": "Học sinh nào",
    "How Many People": "Có mấy người",
    "Age": "Tuổi",
    "Birthday Date": "Ngày sinh nhật",
    "Year and Month": "Năm và tháng",
    "Weekday": "Thứ trong tuần",
    "Good Weather": "Thời tiết đẹp",
    "Too Hot": "Quá nóng",
    "Some Fruit": "Một ít trái cây",
    "Dog": "Chó",
    "Cat": "Mèo",
    "Daughter": "Con gái",
    "Son": "Con trai",
    "Mister and Miss": "Ông và cô",
    "Name": "Tên",
    "Happy": "Vui",
    "Likes": "Thích",
    "Want Water": "Muốn uống nước",
    "Can Come": "Có thể đến",
    "Please Sit": "Mời ngồi",
    "Sorry": "Xin lỗi",
    "Thanks": "Cảm ơn",
    "Goodbye": "Tạm biệt",
    "A Little": "Một chút",
    "Many and Few": "Nhiều và ít",
    "Big and Small": "Lớn và nhỏ",
    "Pretty": "Đẹp",
    "How Is It": "Nó thế nào",
    "Work": "Công việc",
    "Dishes": "Món ăn",
    "Cup": "Cốc",
    "Store Is Open": "Cửa hàng mở cửa",
    "I See You": "Tôi thấy bạn",
    "Return to Beijing": "Trở về Bắc Kinh",
    "Sitting": "Ngồi",
    "Living at Home": "Sống ở nhà",
    "Doing Homework": "Làm bài tập",
    "Writing at School": "Viết ở trường",
    "Classmates": "Bạn cùng lớp",
    "No Money": "Không có tiền",
    "Buying Things": "Mua đồ",
    "Now": "Bây giờ",
    "In Front of Home": "Trước nhà",
    "Everyone at Home": "Mọi người ở nhà",
    "Also a Teacher": "Cũng là giáo viên",
    "Both Like Tea": "Đều thích trà",
    "Morning Call": "Cuộc gọi buổi sáng",
    "Eating at Home": "Ăn ở nhà",
    "Doctor's Question": "Câu hỏi của bác sĩ",
    "Asking for a Book": "Hỏi mượn sách",
    "No Tea": "Không có trà",
    "Review Day": "Ngày ôn tập",
    "HSK1 Mini Passage": "Đoạn đọc ngắn HSK1",
}

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
    ("吗 question", "Statement + 吗?", "Thêm 吗 ở cuối câu trần thuật để tạo câu hỏi có/không.", "你喜欢茶吗？", "Ni3 xi3huan5 cha2 ma5?", "Bạn thích trà không?"),
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
    ("A-not-A question", "Verb + 不 + verb", "Dùng dạng khẳng định-phủ định để hỏi lựa chọn có/không.", "你去不去？", "Ni3 qu4 bu2 qu4?", "Bạn có đi không?"),
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

# Exact English translation for each `explanation` value above (keyed by the
# Vietnamese text, which is unique per grammar point). Used so the EN locale
# shows a translation of the *specific* grammar point instead of one generic
# templated sentence shared by all points at a level.
GRAMMAR_EXPLANATION_EN = {
    "Dùng 是 để xác định danh tính, vai trò hoặc loại sự vật.": "Use 是 to identify a person's identity, role, or a type of thing.",
    "Thêm 吗 ở cuối câu trần thuật để tạo câu hỏi có/không.": "Add 吗 at the end of a statement to turn it into a yes/no question.",
    "Dùng 的 để chỉ sở hữu hoặc quan hệ.": "Use 的 to show possession or a relationship.",
    "Dùng 有 để nói có, 没有 để nói không có.": "Use 有 to say something exists/is owned, and 没有 to say it does not.",
    "Dùng 在 trước địa điểm để nói ai/cái gì ở đâu.": "Use 在 before a place to say who or what is there.",
    "很 thường đứng trước tính từ trong câu miêu tả cơ bản.": "很 usually comes before an adjective in a basic descriptive sentence.",
    "Dùng 想 để nói mong muốn hoặc ý định.": "Use 想 to express a wish or an intention.",
    "Dùng 会 để nói khả năng đã học được.": "Use 会 to talk about a learned ability.",
    "Dùng 去 để nói đi đến một địa điểm.": "Use 去 to say you are going to a place.",
    "Dùng 几 cho số nhỏ dự kiến, 多少 cho số lượng/giá cả rộng hơn.": "Use 几 for a small expected number, and 多少 for a larger quantity or a price.",
    "Từ chỉ thời gian thường đứng trước hoặc sau chủ ngữ.": "Time words usually come before or after the subject.",
    "Dùng 和 để nối danh từ hoặc người.": "Use 和 to connect nouns or people.",
    "也 nghĩa là cũng; 都 nghĩa là đều/tất cả.": "也 means also; 都 means all/every.",
    "Dùng dạng khẳng định-phủ định để hỏi lựa chọn có/không.": "Use the affirmative-negative form (Verb + 不 + Verb) to ask a yes/no question.",
    "了 đánh dấu hành động đã hoàn thành hoặc trạng thái mới.": "了 marks a completed action or a new state.",
    "正在 nhấn mạnh hành động đang diễn ra.": "正在 emphasizes an action currently in progress.",
    "过 nói về kinh nghiệm từng làm việc gì.": "过 talks about past experience of doing something.",
    "Dùng 比 để so sánh hai đối tượng.": "Use 比 to compare two things.",
    "Nêu nguyên nhân rồi kết quả.": "State the cause, then the result.",
    "Dùng để nói điều kiện và kết quả.": "Used to express a condition and its result.",
    "Diễn đạt nhượng bộ và ý tương phản.": "Expresses concession and a contrasting idea.",
    "Diễn đạt hai hành động xảy ra song song.": "Expresses two actions happening at the same time.",
    "Nói phạm vi thời gian hoặc không gian.": "States a range of time or space.",
    "Dùng 离 để nói khoảng cách.": "Use 离 to talk about distance.",
    "Nhấn mạnh cách xử lý đối tượng.": "Emphasizes how an object or task is handled.",
    "Dùng 被 khi đối tượng chịu tác động.": "Use 被 when the subject is affected by an action.",
    "Diễn tả xu hướng ngày càng tăng.": "Expresses an increasing trend.",
    "Nói ngoại trừ hoặc bổ sung ngoài một điều.": "States an exception, or an addition besides one thing.",
    "Phủ định cách hiểu sai và đưa cách hiểu đúng hơn.": "Denies a mistaken interpretation and gives a more accurate one.",
    "So sánh hai lựa chọn và khuyên chọn phương án sau.": "Compares two options and recommends the second one.",
    "Nêu hai mặt, vế sau thường tăng cường ý.": "States two aspects, where the second clause usually reinforces the point.",
    "Dựa vào sự thật đã nêu để đưa quyết định.": "Uses a stated fact as the basis for a decision.",
    "Nêu kết quả trước rồi giải thích nguyên nhân.": "States the result first, then explains the reason.",
    "Diễn đạt bất kể điều kiện nào kết quả vẫn không đổi.": "Expresses that the result stays the same no matter the condition.",
    "Nêu điều kiện duy nhất để tránh kết quả khác.": "States the only condition that avoids a different outcome.",
    "Nói khi một việc xảy ra thì kết quả sẽ lập tức theo sau.": "Says that once something happens, the result follows immediately.",
    "Chọn hy sinh một điều hơn là làm điều không muốn.": "Chooses to give up one thing rather than do something unwanted.",
    "Diễn đạt kết quả trái với dự đoán.": "Expresses a result that is contrary to expectation.",
    "Dùng để rút ra kết luận từ thông tin trước.": "Used to draw a conclusion from information stated earlier.",
    "Giới hạn phạm vi thảo luận.": "Limits the scope of the discussion.",
    "Nêu góc nhìn dùng để đánh giá.": "States the perspective used for the evaluation.",
    "Nói việc gì đáng làm.": "Says that something is worth doing.",
}

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

EN_TERM_VI = {
    meaning_en.lower(): meaning_vi
    for words in LEVEL_WORDS.values()
    for _, _, meaning_vi, meaning_en in words
}
EN_TERM_VI.update(
    {
        "a book": "một cuốn sách",
        "also a book": "cũng là một cuốn sách",
        "age": "tuổi",
        "airport": "sân bay",
        "answer": "đáp án",
        "at home": "ở nhà",
        "at school": "ở trường",
        "bad": "không tốt",
        "beijing": "Bắc Kinh",
        "book": "sách",
        "brand": "thương hiệu",
        "breakfast starts at seven": "Bữa sáng bắt đầu lúc bảy giờ",
        "can i try it on": "Tôi có thể mặc thử không",
        "chair": "ghế",
        "chinese": "tiếng Trung",
        "chinese language": "tiếng Trung",
        "class": "buổi học",
        "classmate": "bạn cùng lớp",
        "clothes": "quần áo",
        "clothing item": "món đồ",
        "cold": "lạnh",
        "come": "đến",
        "computer": "máy tính",
        "correct": "đúng",
        "customer": "khách hàng",
        "dad": "bố",
        "dad, mom, and me": "bố, mẹ và tôi",
        "daughter": "con gái",
        "doctor": "bác sĩ",
        "doctors": "bác sĩ",
        "dog": "chó",
        "eight": "tám",
        "far": "xa",
        "father": "bố",
        "five": "năm",
        "food": "đồ ăn",
        "four": "bốn",
        "friend": "bạn",
        "friends": "những người bạn",
        "family": "gia đình",
        "family/home": "gia đình/nhà",
        "good": "tốt",
        "goodbye": "tạm biệt",
        "hello teacher": "chào thầy/cô",
        "home": "nhà",
        "hospital": "bệnh viện",
        "hotel": "khách sạn",
        "how many people are in your family": "nhà bạn có mấy người",
        "how old your younger sister is": "em gái bạn bao nhiêu tuổi",
        "i": "tôi",
        "it is next to the train station": "Nó ở cạnh ga tàu",
        "luggage": "hành lý",
        "medicine": "thuốc",
        "meeting": "cuộc họp",
        "mom": "mẹ",
        "money": "tiền",
        "morning": "buổi sáng",
        "movie": "phim",
        "my friend": "bạn của tôi",
        "my teacher": "giáo viên của tôi",
        "name": "tên",
        "next to": "bên cạnh",
        "person": "người đó",
        "no": "không",
        "no answer": "chưa trả lời",
        "office": "văn phòng",
        "passport": "hộ chiếu",
        "please put the suitcase here": "Vui lòng đặt vali ở đây",
        "please rest well": "Vui lòng nghỉ ngơi cho tốt",
        "please write ten sentences": "Vui lòng viết mười câu",
        "possession/existence": "sở hữu/tồn tại",
        "price": "giá tiền",
        "question": "câu hỏi",
        "restaurant": "nhà hàng",
        "room": "phòng",
        "school": "trường học",
        "she": "cô ấy",
        "speaker": "người nói",
        "she is eight years old": "Cô ấy tám tuổi",
        "shop assistant": "nhân viên bán hàng",
        "sorry": "xin lỗi",
        "staff": "nhân viên",
        "student": "học sinh",
        "student identity": "thân phận học sinh",
        "students": "học sinh",
        "subway station": "ga tàu điện ngầm",
        "teacher": "giáo viên",
        "teachers": "giáo viên",
        "tea": "trà",
        "thank you": "cảm ơn",
        "the meeting is in the office": "Cuộc họp ở văn phòng",
        "three": "ba",
        "ticket": "vé",
        "to buy": "mua",
        "train station": "ga tàu",
        "water": "nước",
        "the customer": "khách hàng",
        "the doctor": "bác sĩ",
        "the friends": "những người bạn",
        "the person": "người đó",
        "the speaker": "người nói",
        "the staff": "nhân viên",
        "the student": "học sinh",
        "the teacher": "giáo viên",
        "where shall we meet": "Chúng ta gặp nhau ở đâu",
        "whether you have water": "bạn có nước hay không",
        "ask": "hỏi",
        "buy": "mua",
        "drink": "uống",
        "eat": "ăn",
        "have": "có",
        "like": "thích",
        "order": "gọi món",
        "say": "nói",
        "study": "học",
        "want": "muốn",
        "watch": "xem",
        "write": "viết",
        "yes": "có",
        "you": "bạn",
        "younger sister": "em gái",
    }
)

VI_TEXT_EN = {
    "Bạn tên là gì?": "What is your name?",
    "Bài đọc nói 学生先听老师说.": "The passage says 学生先听老师说.",
    "Câu 我是学生 cho biết An An là học sinh.": "The sentence 我是学生 shows that An An is a student.",
    "Câu 因为地址有错误，所以快递还没到 nêu nguyên nhân.": "The sentence 因为地址有错误，所以快递还没到 gives the reason.",
    "Câu đầy đủ: 今天我们学习": "Full sentence: 今天我们学习",
    "Cụm 在学校门口 cho biết địa điểm.": "The phrase 在学校门口 shows the meeting place.",
    "Cư dân đề xuất điều gì?": "What do the residents suggest?",
    "Cuối tuần bạn có thời gian không?": "Do you have time this weekend?",
    "Dùng 叫 để giới thiệu hoặc hỏi tên. Không thêm 是 giữa chủ ngữ và 叫.": "Use 叫 to introduce or ask for names. Do not add 是 between the subject and 叫.",
    "Dùng 是 chủ yếu để nối với danh từ hoặc vai trò.": "Use 是 mainly before nouns or roles.",
    "Dùng 是 để nói ai là ai hoặc ai thuộc vai trò nào.": "Use 是 to say who someone is or what role they have.",
    "Dùng để nối nguyên nhân và kết quả. Trong tiếng Trung có thể dùng cả 因为 và 所以 cùng lúc.": "Use this to connect cause and result. In Chinese, 因为 and 所以 can appear together.",
    "Dùng để nêu hai ý tương phản: công nhận một mặt, sau đó nhấn mạnh mặt khác.": "Use this to express contrast: acknowledge one side, then emphasize another.",
    "Dùng để phủ định một cách hiểu chưa chính xác và đưa ra ý đúng hơn.": "Use this to reject an inaccurate understanding and give a better one.",
    "Dùng để so sánh hai lựa chọn và khuyên chọn phương án tốt hơn.": "Use this to compare two choices and recommend the better one.",
    "Dùng 建议 để đưa đề xuất. Có thể dịch là đề nghị/khuyên.": "Use 建议 to make a suggestion. It can mean suggest or advise.",
    "Gạch chân các câu dùng 是.": "Underline the sentences that use 是.",
    "Gạch chân các từ liên quan đến dịch vụ giao hàng.": "Underline words related to delivery service.",
    "Hỏi tên bạn học bằng mẫu: 你叫什么名字？": "Ask a classmate's name with the pattern 你叫什么名字？",
    "Không dùng 是 trước tính từ ở HSK1 như 我是好.": "Do not use 是 before adjectives in HSK1 sentences such as 我是好.",
    "Không đặt 想 sau động từ: sai 看想电影.": "Do not put 想 after the verb: 看想电影 is incorrect.",
    "Không đảo kết quả lên trước khi dùng 所以.": "Do not move the result before 所以.",
    "Không dịch theo thứ tự tiếng Việt một cách máy móc.": "Do not copy Vietnamese word order mechanically.",
    "Không dùng 但是 để lặp lại cùng ý; vế sau cần có tương phản.": "Do not use 但是 to repeat the same idea; the second clause needs contrast.",
    "Nghe và ghi lại hai thông tin người nói yêu cầu.": "Listen and write down the two details the speaker requests.",
    "Nghe và ghi lại thời gian hẹn.": "Listen and write down the meeting time.",
    "Nghe và xác định cấu trúc sửa ý sai cùng cấu trúc đưa lời khuyên.": "Listen and identify the correction pattern and the advice pattern.",
    "Nghe và xác định người nói đang hỏi điều gì.": "Listen and identify what the speaker is asking.",
    "Nghe và xác định vấn đề cùng đề xuất.": "Listen and identify the issue and the suggestion.",
    "Người nói gặp bạn ở đâu?": "Where does the speaker meet the friend?",
    "Người nói đang hỏi tên.": "The speaker is asking for a name.",
    "Nhập một từ/cụm xuất hiện trong bài đọc.": "Enter one word or phrase that appears in the reading.",
    "Nói 3 câu ngắn về": "Say 3 short sentences about",
    "Nói tuổi của ai đó.": "Say someone's age.",
    "Nêu một vấn đề trong khu bạn sống bằng 虽然...但是....": "Describe a problem in your neighborhood with 虽然...但是....",
    "Theo bài đọc, hiệu suất học phụ thuộc vào điều gì?": "According to the reading, what does study efficiency depend on?",
    "Tìm câu có 因为...所以....": "Find the sentence with 因为...所以....",
    "Tìm câu mô tả tác động của tiếng ồn.": "Find the sentence that describes the impact of noise.",
    "Tìm câu nêu luận điểm chính.": "Find the sentence that states the main argument.",
    "Tìm các từ chỉ thời gian trong đoạn đọc.": "Find the time words in the passage.",
    "Tìm địa điểm hẹn gặp.": "Find the meeting place.",
    "Tìm tên người trong đoạn đọc.": "Find the names in the reading.",
    "Tách bài đọc thành: hiểu lầm, ý đúng, lời khuyên.": "Separate the reading into misunderstanding, correction, and advice.",
    "Tự giới thiệu bằng mẫu: 你好，我叫...": "Introduce yourself with the pattern 你好，我叫...",
    "Từ chỉ thời gian thường đứng trước hành động chính.": "Time words usually appear before the main action.",
    "Vì sao bưu kiện chưa đến?": "Why has the package not arrived?",
    "Viết 2 câu giới thiệu một giáo viên hoặc một người bạn.": "Write 2 sentences introducing a teacher or a friend.",
    "Viết 3 câu giới thiệu bản thân.": "Write 3 sentences introducing yourself.",
    "Viết một tin nhắn 3 câu rủ bạn đi chơi cuối tuần.": "Write a 3-sentence message inviting a friend out this weekend.",
    "Viết một tin nhắn 4 câu yêu cầu sửa địa chỉ giao hàng.": "Write a 4-sentence message asking someone to fix a delivery address.",
    "Viết một đoạn 5 câu về một vấn đề trong cộng đồng và cách giải quyết.": "Write a 5-sentence paragraph about a community problem and solution.",
    "Viết đoạn 6 câu về cách tăng hiệu suất học HSK, dùng cả hai cấu trúc ngữ pháp của bài.": "Write a 6-sentence paragraph about improving HSK study efficiency using both grammar patterns.",
    "Vấn đề: 噪音影响休息; đề xuất: 减少音乐": "Issue: 噪音影响休息; suggestion: 减少音乐",
    "Đoạn đọc nói 居民建议商店十点以后减少音乐.": "The passage says 居民建议商店十点以后减少音乐.",
    "Đoạn đọc nói 效率取决于学习者是否有自主计划.": "The passage says 效率取决于学习者是否有自主计划.",
    "Đưa một đề xuất với 我建议....": "Make a suggestion with 我建议....",
    "Đưa một lời khuyên học tập bằng 与其...不如....": "Give study advice with 与其...不如....",
    "Đúng: 我叫安安。": "Correct: 我叫安安。",
    "Đúng: 想看电影.": "Correct: 想看电影.",
}

EN_TEXT_VI = {
    "Answer simple comprehension questions.": "Trả lời các câu hỏi đọc hiểu đơn giản.",
    "Ask and answer names with 叫.": "Hỏi và trả lời tên bằng 叫.",
    "Build first-person, second-person, and third-person recognition.": "Xây dựng khả năng nhận diện ngôi thứ nhất, thứ hai và thứ ba.",
    "Choose the best meaning.": "Chọn nghĩa phù hợp nhất.",
    "Choose the matching Chinese word.": "Chọn từ tiếng Trung phù hợp.",
    "Choose the matching phrase.": "Chọn cụm phù hợp.",
    "Choose the matching word.": "Chọn từ phù hợp.",
    "Discuss a community issue with clear reasons.": "Thảo luận một vấn đề cộng đồng với lý do rõ ràng.",
    "Discuss online learning with abstract vocabulary.": "Thảo luận việc học trực tuyến bằng từ vựng trừu tượng.",
    "Explain a delivery address problem.": "Giải thích vấn đề về địa chỉ giao hàng.",
    "Form identity sentences": "Tạo câu nhận diện danh tính.",
    "Give suggestions with 建议 and 应该.": "Đưa góp ý bằng 建议 và 应该.",
    "Greet people naturally in simple situations.": "Chào hỏi tự nhiên trong các tình huống đơn giản.",
    "Learn to greet someone, say your name, and identify yourself as a student or teacher.": "Học cách chào hỏi, nói tên và giới thiệu mình là học sinh hoặc giáo viên.",
    "Negate identity sentences": "Phủ định câu nhận diện danh tính.",
    "No answer": "Chưa trả lời",
    "Practice input, output, and quiz recall in one short session.": "Luyện đầu vào, đầu ra và ghi nhớ qua quiz trong một buổi ngắn.",
    "Read a short HSK1 passage and answer comprehension questions.": "Đọc một đoạn ngắn HSK1 và trả lời câu hỏi đọc hiểu.",
    "Read a short HSK1 text with familiar words.": "Đọc một đoạn HSK1 ngắn với các từ quen thuộc.",
    "Recognize basic pronouns": "Nhận diện các đại từ cơ bản.",
    "Talk about weekend plans with 想 and 要.": "Nói về kế hoạch cuối tuần bằng 想 và 要.",
    "This lesson builds the first communication loop: greet, introduce yourself, ask a name, and identify a role. It prepares learners for short classroom conversations.": "Bài này xây dựng vòng giao tiếp đầu tiên: chào hỏi, tự giới thiệu, hỏi tên và xác định vai trò. Bài chuẩn bị cho hội thoại lớp học ngắn.",
    "This unit connects time, place, and intention. Learners move from isolated sentences to a short plan: when to go, where to meet, and what to do.": "Bài này nối thời gian, địa điểm và ý định. Người học chuyển từ câu riêng lẻ sang một kế hoạch ngắn: đi khi nào, gặp ở đâu và làm gì.",
    "This unit develops opinion language. Learners describe a problem, explain its influence, and propose a realistic solution.": "Bài này phát triển ngôn ngữ nêu ý kiến. Người học mô tả vấn đề, giải thích ảnh hưởng và đề xuất giải pháp thực tế.",
    "This unit moves from daily planning to problem-solving. Learners practice describing what went wrong and asking staff to correct information.": "Bài này chuyển từ lập kế hoạch hằng ngày sang giải quyết vấn đề. Người học luyện mô tả lỗi phát sinh và nhờ nhân viên sửa thông tin.",
    "This unit prepares HSK5 learners for opinion and argument tasks. It teaches how to make a claim, correct a misunderstanding, and support a practical recommendation.": "Bài này chuẩn bị cho người học HSK5 làm nhiệm vụ nêu ý kiến và lập luận. Bài dạy cách đưa luận điểm, sửa hiểu lầm và hỗ trợ một khuyến nghị thực tế.",
    "Use 因为...所以... for cause and result.": "Dùng 因为...所以... để nói nguyên nhân và kết quả.",
    "Use 并不是...而是... to correct an assumption.": "Dùng 并不是...而是... để sửa một giả định.",
    "Use 想 and 要 to talk about future plans.": "Dùng 想 và 要 để nói về kế hoạch tương lai.",
    "Use 把 to describe handling an object or task.": "Dùng 把 để mô tả việc xử lý một đồ vật hoặc nhiệm vụ.",
    "Use 是 to identify people and roles.": "Dùng 是 để xác định người và vai trò.",
    "Use 虽然...但是... to contrast ideas.": "Dùng 虽然...但是... để tương phản ý.",
    "Use 与其...不如... to compare choices.": "Dùng 与其...不如... để so sánh lựa chọn.",
    "What is the main topic of this lesson?": "Chủ đề chính của bài này là gì?",
}

# Extra learning-content phrases (multiple-choice options, quiz answers/questions,
# learning objectives, task labels, reading/dialogue titles) that are generated
# combinatorially and therefore need explicit translations rather than relying on
# the fallback word-substitution in `_translate_fragment_vi`.
EN_TEXT_VI.update(
    {
        # Reading / dialogue titles
        "A Delivery Mistake": "Một lỗi giao hàng",
        "A Neighborhood Suggestion": "Một góp ý cho khu dân cư",
        "Online Learning Advice": "Lời khuyên về học trực tuyến",
        # Grammar point titles
        "A-not-A question": "Câu hỏi dạng A-không-A",
        "Time before action": "Thời gian đứng trước hành động",
        # Learning objectives
        "Add supporting information": "Bổ sung thông tin hỗ trợ",
        "Assess HSK2 daily-life communication": "Đánh giá khả năng giao tiếp đời thường HSK2",
        "Assess HSK3 practical communication": "Đánh giá khả năng giao tiếp thực tế HSK3",
        "Assess HSK4 connector and inference skills": "Đánh giá kỹ năng dùng liên từ và suy luận HSK4",
        "Assess HSK5 argument and inference skills": "Đánh giá kỹ năng lập luận và suy luận HSK5",
        "Assess advanced HSK6 reading, listening, and reasoning": "Đánh giá kỹ năng đọc, nghe và lập luận nâng cao HSK6",
        "Assess first HSK1 communication patterns": "Đánh giá các mẫu giao tiếp đầu tiên của HSK1",
        "Borrow and return books": "Mượn và trả sách",
        "Build contrast sentences": "Xây dựng câu tương phản",
        "Build short introductions": "Xây dựng đoạn giới thiệu ngắn",
        "Confirm phone and address details": "Xác nhận số điện thoại và địa chỉ",
        "Connect causes and results": "Kết nối nguyên nhân và kết quả",
        "Connect reasons and suggestions": "Kết nối lý do và đề xuất",
        "Create a weekend schedule": "Lập lịch trình cuối tuần",
        "Describe completed handling actions": "Mô tả hành động xử lý đã hoàn thành",
        "Describe daily routines": "Mô tả hoạt động thường ngày",
        "Exchange names": "Trao đổi tên gọi",
        "Follow an academic explanation": "Theo dõi một lời giải thích học thuật",
        "Form conditional sentences": "Tạo câu điều kiện",
        "Frame analytical points": "Xây dựng các luận điểm phân tích",
        "Give practical advice": "Đưa ra lời khuyên thực tế",
        "Identify address and payment details": "Xác định địa chỉ và thông tin thanh toán",
        "Identify cause and recommendation": "Xác định nguyên nhân và khuyến nghị",
        "Identify location and task": "Xác định vị trí và nhiệm vụ",
        "Identify opinion and suggestion": "Xác định ý kiến và đề xuất",
        "Produce structured advanced responses": "Tạo phản hồi nâng cao có cấu trúc",
        "Qualify abstract claims": "Bổ nghĩa cho các luận điểm trừu tượng",
        "Read a problem-solution paragraph": "Đọc một đoạn văn nêu vấn đề và giải pháp",
        "Read a short self-introduction": "Đọc một đoạn tự giới thiệu ngắn",
        "Read an abstract social-analysis passage": "Đọc một đoạn văn phân tích xã hội trừu tượng",
        "Read an argumentative paragraph": "Đọc một đoạn văn lập luận",
        "Recognize abstract topic vocabulary": "Nhận diện từ vựng chủ đề trừu tượng",
        "Request a correction": "Yêu cầu sửa lại thông tin",
        "State a reasoned alternative": "Nêu một lựa chọn thay thế có lý do",
        "State nuanced conclusions": "Nêu kết luận có sắc thái",
        "Support an opinion with reasons": "Hỗ trợ ý kiến bằng lý do",
        "Talk about simple activities": "Nói về các hoạt động đơn giản",
        "Track argument flow": "Theo dõi mạch lập luận",
        "Understand a workplace reminder": "Hiểu một lời nhắc việc tại nơi làm việc",
        "Understand advice about stress": "Hiểu lời khuyên về căng thẳng",
        "Understand greetings": "Hiểu các lời chào hỏi",
        "Understand interview answers": "Hiểu các câu trả lời phỏng vấn",
        "Use advanced transitions": "Sử dụng từ chuyển ý nâng cao",
        "Use analytical vocabulary": "Sử dụng từ vựng phân tích",
        "Use degree words naturally": "Sử dụng từ chỉ mức độ một cách tự nhiên",
        "Use polite beginner greetings": "Sử dụng lời chào lịch sự cho người mới học",
        # Overview / focus summaries
        "Advanced analytical words for social, academic, and essay contexts.": "Từ vựng phân tích nâng cao cho ngữ cảnh xã hội, học thuật và viết luận.",
        "Formal discussion vocabulary for media and public topics.": "Từ vựng thảo luận trang trọng cho chủ đề truyền thông và công chúng.",
        "Intermediate social topics and city-life vocabulary.": "Chủ đề xã hội trung cấp và từ vựng đời sống thành phố.",
        "Problem statements and practical solution vocabulary.": "Từ vựng nêu vấn đề và giải pháp thực tế.",
        "Routine verbs and healthy daily habits.": "Động từ thường ngày và thói quen sống lành mạnh.",
        "Shopping": "Mua sắm",
        # Reading / speaking task labels (short topic tags)
        "academic framing": "cách diễn đạt học thuật",
        "argument structure": "cấu trúc lập luận",
        "career interview": "phỏng vấn nghề nghiệp",
        "choose best advice response": "chọn phản hồi lời khuyên phù hợp nhất",
        "choose comparison forms": "chọn cấu trúc so sánh",
        "city life": "đời sống thành phố",
        "combine contrast clauses": "kết hợp các mệnh đề tương phản",
        "conditions": "điều kiện",
        "daily actions": "hoạt động hằng ngày",
        "discourse transitions": "từ chuyển ý trong diễn ngôn",
        "formal connectors": "liên từ trang trọng",
        "greetings": "lời chào hỏi",
        "health habits": "thói quen sức khỏe",
        "identify thesis": "xác định luận điểm chính",
        "map argument structure": "sơ đồ hóa cấu trúc lập luận",
        "match pronouns": "nối đại từ phù hợp",
        "media topics": "chủ đề truyền thông",
        "problem statements": "câu nêu vấn đề",
        "pronouns": "đại từ",
        "reasons": "lý do",
        "respond to an interview prompt": "trả lời một câu hỏi phỏng vấn",
        "rewrite with formal patterns": "viết lại bằng mẫu câu trang trọng",
        "skills": "kỹ năng",
        "social analysis": "phân tích xã hội",
        "summarize a community issue": "tóm tắt một vấn đề trong cộng đồng",
        # Multiple-choice quiz options / answers (short vocabulary-level phrases)
        "A cat": "Một con mèo",
        "A little": "Một ít",
        "A lot": "Nhiều",
        "A phone": "Một chiếc điện thoại",
        "All": "Tất cả",
        "At noon": "Vào buổi trưa",
        "At the store": "Ở cửa hàng",
        "Behind": "Phía sau",
        "Big": "To",
        "Bird": "Chim",
        "Buying apples": "Mua táo",
        "Buying things": "Mua đồ",
        "Call": "Gọi điện",
        "Cats": "Những con mèo",
        "Characters": "Chữ Hán",
        "Coffee": "Cà phê",
        "English": "Tiếng Anh",
        "February 1": "Ngày 1 tháng 2",
        "Fine": "Ổn",
        "Fish": "Cá",
        "Fly": "Bay",
        "Friday": "Thứ Sáu",
        "Fruit": "Trái cây",
        "Fruit and apples": "Trái cây và táo",
        "Horse": "Ngựa",
        "Hot": "Nóng",
        "How much": "Bao nhiêu tiền",
        "How old someone is": "Tuổi của ai đó",
        "In front": "Phía trước",
        "In the taxi": "Trong xe taxi",
        "It opened": "Nó đã mở",
        "It's okay": "Không sao",
        "January": "Tháng Một",
        "January 1": "Ngày 1 tháng 1",
        "January 2": "Ngày 2 tháng 1",
        "July": "Tháng Bảy",
        "June": "Tháng Sáu",
        "Location": "Vị trí",
        "Many cats": "Nhiều con mèo",
        "Many chairs only": "Chỉ có nhiều ghế",
        "Many dishes": "Nhiều món ăn",
        "March 3": "Ngày 3 tháng 3",
        "Milk": "Sữa",
        "Monday": "Thứ Hai",
        "My son": "Con trai tôi",
        "None": "Không có gì",
        "Noon": "Buổi trưa",
        "Not stated": "Không được nêu rõ",
        "October": "Tháng Mười",
        "On the table": "Trên bàn",
        "Only a plane": "Chỉ có máy bay",
        "Only at noon": "Chỉ vào buổi trưa",
        "Only by phone": "Chỉ qua điện thoại",
        "Only numbers": "Chỉ có số",
        "Open a store": "Mở một cửa hàng",
        "Please sit": "Xin hãy ngồi",
        "Rainy": "Mưa",
        "Read": "Đọc",
        "Reading books": "Đọc sách",
        "Reads": "Đọc",
        "Shop": "Cửa hàng",
        "Sleep only": "Chỉ ngủ",
        "Sleeping": "Đang ngủ",
        "Small": "Nhỏ",
        "Small and pretty": "Nhỏ và xinh",
        "Speak": "Nói",
        "Store": "Cửa hàng",
        "Sunday": "Chủ Nhật",
        "Sunny": "Nắng",
        "TV": "Ti vi",
        "Taxi": "Xe taxi",
        "The 2nd": "Ngày 2",
        "The place": "Địa điểm đó",
        "This dish": "Món này",
        "Tired": "Mệt",
        "Too hot": "Quá nóng",
        "Tuesday": "Thứ Ba",
        "Twenty": "Hai mươi",
        "Watching movies": "Xem phim",
        "What this is": "Đây là cái gì",
        "Where": "Ở đâu",
        "Which one": "Cái nào",
        "Who": "Ai",
        # Reading-comprehension / quiz questions
        "What month is it now?": "Bây giờ là tháng mấy?",
        "What place is asked about?": "Địa điểm nào được hỏi đến?",
        "What request is made?": "Yêu cầu nào được đưa ra?",
        "What transportation is used?": "Phương tiện di chuyển nào được dùng?",
        "Where are they?": "Họ ở đâu?",
        "Where do they go?": "Họ đi đâu?",
        "Where do they live?": "Họ sống ở đâu?",
        "Where do they stay?": "Họ ở lại đâu?",
        "Who also comes?": "Ai cũng đến?",
        "Who also likes apples?": "Ai cũng thích táo?",
        "Who also reads?": "Ai cũng đọc?",
        "Who also watches?": "Ai cũng xem?",
        "Who speaks first?": "Ai nói trước?",
        "Who watches?": "Ai xem?",
        # Grammar explanations that mix Chinese words with an English gloss
        # (the Chinese stays unchanged; only the English commentary is translated).
        "昨天 and 今天 show the timing of two actions.": "昨天 và 今天 cho biết thời điểm của hai hành động.",
        "上午 and 下午 appear before the actions.": "上午 và 下午 đứng trước hành động.",
        "在饭店 gives the location of the action 吃米饭.": "在饭店 cho biết địa điểm của hành động 吃米饭.",
        "汉语 is used as the object of both 学习 and 说.": "汉语 được dùng làm tân ngữ cho cả 学习 và 说.",
        "前面 and 上 are location words.": "前面 và 上 là các từ chỉ vị trí.",
        "Place + 有 introduces things that exist in that place.": "Địa điểm + 有 dùng để nêu những gì tồn tại ở nơi đó.",
        "写字 is the action, and 在学校 gives the location.": "写字 là hành động, còn 在学校 cho biết địa điểm.",
        "不去 negates going, and 在家吃饭 gives the alternative.": "不去 phủ định việc đi, còn 在家吃饭 nêu lựa chọn thay thế.",
        "星期天 gives the day, and 在家 gives the location.": "星期天 cho biết ngày, còn 在家 cho biết địa điểm.",
        # Multiple-choice options and short answers that previously fell through to
        # the word-by-word fragment translator, producing mixed English/Vietnamese
        # strings (e.g. "At the trường học gate"). Each entry below is a full,
        # natural Vietnamese translation of the whole phrase.
        "At the airport": "Ở sân bay",
        "At the hospital": "Ở bệnh viện",
        "At the hotel": "Ở khách sạn",
        "At the hotel front desk": "Ở lễ tân khách sạn",
        "At the office": "Ở văn phòng",
        "At the restaurant": "Ở nhà hàng",
        "At the school gate": "Ở cổng trường",
        "At/in home": "Ở nhà",
        "Behind the chair": "Sau cái ghế",
        "Behind the doctor": "Sau bác sĩ",
        "Clothes and receipt": "Quần áo và hóa đơn",
        "Clothes and shoes": "Quần áo và giày",
        "Cold and rainy": "Lạnh và có mưa",
        "Cold and tired": "Lạnh và mệt",
        "Computer and documents": "Máy tính và tài liệu",
        "Do you have breakfast?": "Bạn có ăn sáng không?",
        "Do you have homework?": "Bạn có bài tập về nhà không?",
        "Do you have luggage?": "Bạn có hành lý không?",
        "Do you have medicine?": "Bạn có thuốc không?",
        "Do you have time on the weekend?": "Bạn có thời gian vào cuối tuần không?",
        "Drink more water and rest": "Uống nhiều nước hơn và nghỉ ngơi",
        "Go back home": "Quay về nhà",
        "Go home": "Về nhà",
        "Go to a meeting": "Đi họp",
        "Go to school": "Đi học",
        "Go to the airport": "Đi đến sân bay",
        "Go to the hospital": "Đi đến bệnh viện",
        "He is a student": "Anh ấy là học sinh",
        "Homework and book": "Bài tập về nhà và sách",
        "How are you?": "Bạn khỏe không?",
        "How much clothes cost": "Quần áo giá bao nhiêu",
        "How much money": "Bao nhiêu tiền",
        "How much the book is": "Sách giá bao nhiêu",
        "How old you are": "Bạn bao nhiêu tuổi",
        "I, dad, and mom": "Tôi, bố và mẹ",
        "In front of the school": "Trước cổng trường",
        "In the hospital": "Trong bệnh viện",
        "In the morning": "Vào buổi sáng",
        "In the school": "Trong trường",
        "Is there a hotel nearby?": "Gần đây có khách sạn không?",
        "It is at school": "Đang ở trường",
        "It is cold": "Trời lạnh",
        "It is cold and raining": "Trời lạnh và có mưa",
        "It is not cold": "Trời không lạnh",
        "Medicine and water": "Thuốc và nước",
        "My friend and I": "Tôi và bạn tôi",
        "My name is An An": "Tên tôi là An An",
        "Number of people in the family": "Số người trong gia đình",
        "Old and expensive": "Cũ và đắt",
        "On the chair": "Trên ghế",
        "Only in the morning": "Chỉ vào buổi sáng",
        "Passport and luggage": "Hộ chiếu và hành lý",
        "Passport and ticket": "Hộ chiếu và vé",
        "Room card and medicine": "Thẻ phòng và thuốc",
        "Room card and passport": "Thẻ phòng và hộ chiếu",
        "School gate": "Cổng trường",
        "She is a teacher": "Cô ấy là giáo viên",
        "Table, chairs, and computer": "Bàn, ghế và máy tính",
        "Teacher and doctor": "Giáo viên và bác sĩ",
        "The customer paid twice": "Khách hàng đã trả tiền hai lần",
        "The name": "Tên",
        "The phone number is correct": "Số điện thoại đúng",
        "The staff is a teacher": "Nhân viên là giáo viên",
        "The time": "Thời gian",
        "The weather": "Thời tiết",
        "Ticket and suitcase": "Vé và vali",
        "To see a doctor": "Đi khám bác sĩ",
        "What is your name?": "Bạn tên là gì?",
        "What time": "Giờ nào",
        "What time it is": "Mấy giờ rồi",
        "What to eat": "Ăn gì",
        "What we study today": "Hôm nay chúng ta học gì",
        "What you drink": "Bạn uống gì",
        "What you eat": "Bạn ăn gì",
        "What you want to eat": "Bạn muốn ăn gì",
        "What your dad eats": "Bố bạn ăn gì",
        "When the meeting starts": "Khi nào cuộc họp bắt đầu",
        "Where are you?": "Bạn đang ở đâu?",
        "Where is the office?": "Văn phòng ở đâu?",
        "Where is the school?": "Trường ở đâu?",
        "Where school is": "Trường ở đâu",
        "Where the teacher is": "Giáo viên ở đâu",
        "Where we go today": "Hôm nay chúng ta đi đâu",
        "Where you live": "Bạn sống ở đâu",
        "Where your mom works": "Mẹ bạn làm việc ở đâu",
        "Whether the teacher has a book": "Giáo viên có sách hay không",
        "Whether tomorrow's weather is good": "Ngày mai thời tiết có tốt hay không",
        "Which student is your friend": "Học sinh nào là bạn của bạn",
        "Who he is": "Anh ấy là ai",
        "Who is a teacher": "Ai là giáo viên",
        "Who she is": "Cô ấy là ai",
        "Who the teacher is": "Giáo viên là ai",
        "Who your teacher is": "Giáo viên của bạn là ai",
        "Your medicine": "Thuốc của bạn",
        "Your room card": "Thẻ phòng của bạn",
        "Your ticket": "Vé của bạn",
        "airport gate": "cổng sân bay",
        "at the school entrance": "ở cổng trường",
        "to have a fever": "bị sốt",
        "to have a meeting": "có cuộc họp",
        "to try clothes": "thử quần áo",
        # Prompts with no matching sentence pattern above (question-answer context
        # from `conversation_quizzes.json`).
        "When should the homework be handed in?": "Bài tập về nhà nên nộp khi nào?",
        "Where will they meet?": "Họ sẽ gặp nhau ở đâu?",
        "Which word connects a contrast?": "Từ nào dùng để nối ý tương phản?",
        "Which boarding gate does the traveler need?": "Hành khách cần cổng lên máy bay số nào?",
        "What surname does the guest give?": "Khách cho biết họ là gì?",
        "When is colleague B available?": "Đồng nghiệp B có thời gian khi nào?",
        "Tomorrow morning": "Sáng ngày mai",
        "Today afternoon": "Chiều nay",
        "Next week": "Tuần sau",
        "Tonight": "Tối nay",
        "At the school entrance": "Ở cổng trường",
        "At the train station": "Ở nhà ga",
        "Gate 8": "Cổng số 8",
        "Gate 6": "Cổng số 6",
        "Gate 3": "Cổng số 3",
        "Gate 10": "Cổng số 10",
        "After 10 a.m.": "Sau 10 giờ sáng",
        "Before 8 a.m.": "Trước 8 giờ sáng",
        "After 3 p.m.": "Sau 3 giờ chiều",
        # HSK1 reading-passage comprehension questions/answers/explanations
        # (`hsk1_reading_passages.json`). These full-sentence entries take
        # precedence over the compositional pattern translators below, which
        # cannot safely translate arbitrary multi-word captured groups (e.g.
        # noun phrases like "the weather today") without leaving a broken
        # mixed-language remainder.
        "How is that store?": "Cửa hàng đó thế nào?",
        "How is the cat?": "Con mèo thế nào?",
        "How is the chair?": "Cái ghế thế nào?",
        "How is the computer?": "Máy tính thế nào?",
        "How is the dog?": "Con chó thế nào?",
        "How is the hotel?": "Khách sạn thế nào?",
        "How is the movie?": "Bộ phim thế nào?",
        "How is the water?": "Nước thế nào?",
        "How is the weather in July?": "Thời tiết tháng Bảy thế nào?",
        "How is the weather?": "Thời tiết thế nào?",
        "How is this school?": "Trường này thế nào?",
        "How many people are in my family?": "Gia đình tôi có mấy người?",
        "How much Chinese can the person speak?": "Người đó nói được bao nhiêu tiếng Trung?",
        "What animal does she have?": "Cô ấy có con vật gì?",
        "What animal is at home?": "Ở nhà có con vật gì?",
        "What are they doing?": "Họ đang làm gì?",
        "What are we all?": "Chúng ta đều là gì?",
        "What are we?": "Chúng ta là gì?",
        "What do they eat?": "Họ ăn gì?",
        "What do they like drinking?": "Họ thích uống gì?",
        "What do they watch?": "Họ xem gì?",
        "What do we all study?": "Chúng ta đều học gì?",
        "What do we study?": "Chúng ta học gì?",
        "What does the person do in the afternoon?": "Người đó làm gì vào buổi chiều?",
        "What does the person do in the morning?": "Người đó làm gì vào buổi sáng?",
        "What does the person not do?": "Người đó không làm gì?",
        "What does the person not have?": "Người đó không có gì?",
        "What does the person study today?": "Hôm nay người đó học gì?",
        "What does the person want to do?": "Người đó muốn làm gì?",
        "What does the restaurant have?": "Nhà hàng có gì?",
        "What does the school have many of?": "Trường có nhiều gì?",
        "What does the speaker not have?": "Người nói không có gì?",
        "What does the speaker want to drink?": "Người nói muốn uống gì?",
        "What is behind the home?": "Sau nhà có gì?",
        "What is in front of the home?": "Trước nhà có gì?",
        "What is in front of the table?": "Trước cái bàn có gì?",
        "What is in the cup?": "Trong cốc có gì?",
        "What is not at home?": "Cái gì không có ở nhà?",
        "What is that one?": "Cái đó là gì?",
        "What is the listener asked about?": "Người nghe được hỏi về điều gì?",
        "What is the response?": "Câu trả lời là gì?",
        "What is the weather today?": "Hôm nay thời tiết thế nào?",
        "What is this one?": "Cái này là gì?",
        "What is this?": "Đây là gì?",
        "What language can he speak?": "Anh ấy nói được ngôn ngữ gì?",
        "What nationality is he?": "Anh ấy là người nước nào?",
        "What question is asked?": "Câu hỏi nào được đặt ra?",
        "What question word is used?": "Từ hỏi nào được dùng?",
        "What time is it?": "Mấy giờ rồi?",
        "What word means name?": "Từ nào có nghĩa là tên?",
        "When do the students go home?": "Khi nào học sinh về nhà?",
        "When does dad go?": "Bố đi khi nào?",
        "When does mom call?": "Mẹ gọi điện khi nào?",
        "When does the person eat?": "Người đó ăn khi nào?",
        "When does the person study?": "Người đó học khi nào?",
        "When is the person asked to come?": "Người đó được yêu cầu đến khi nào?",
        "When is the weather cold?": "Khi nào thời tiết lạnh?",
        "Where are the students?": "Học sinh ở đâu?",
        "Where do the speaker and friend go?": "Người nói và bạn đi đâu?",
        "Where do they eat?": "Họ ăn ở đâu?",
        "Where does dad go?": "Bố đi đâu?",
        "Where does dad return?": "Bố trở về đâu?",
        "Where does dad work?": "Bố làm việc ở đâu?",
        "Where does mom work?": "Mẹ làm việc ở đâu?",
        "Where does she go?": "Cô ấy đi đâu?",
        "Where does she read?": "Cô ấy đọc ở đâu?",
        "Where does the person go?": "Người đó đi đâu?",
        "Where does the person live?": "Người đó sống ở đâu?",
        "Where does the person study Chinese?": "Người đó học tiếng Trung ở đâu?",
        "Where does the person work?": "Người đó làm việc ở đâu?",
        "Where does the student sit?": "Học sinh ngồi ở đâu?",
        "Where does the teacher not go?": "Giáo viên không đi đâu?",
        "Where is it?": "Nó ở đâu?",
        "Where is the book?": "Sách ở đâu?",
        "Where is the caller?": "Người gọi điện ở đâu?",
        "Where is the cup?": "Cốc ở đâu?",
        "Where is the fruit?": "Trái cây ở đâu?",
        "Where is the person today?": "Hôm nay người đó ở đâu?",
        "Where is the speaker now?": "Bây giờ người nói ở đâu?",
        "Where will the person go tomorrow?": "Ngày mai người đó sẽ đi đâu?",
        "Which dish does the speaker like?": "Người nói thích món nào?",
        "Who also goes home?": "Ai cũng về nhà?",
        "Who also says goodbye?": "Ai cũng chào tạm biệt?",
        "Who comes to school in the morning?": "Ai đến trường vào buổi sáng?",
        "Who does the person see?": "Người đó gặp ai?",
        "Who does the speaker see?": "Người nói gặp ai?",
        "Who does the student listen to?": "Học sinh nghe ai?",
        "Who goes to the hospital?": "Ai đi đến bệnh viện?",
        "Who has money?": "Ai có tiền?",
        "Who is also at school?": "Ai cũng ở trường?",
        "Who is in front?": "Ai ở phía trước?",
        "Who is in the family?": "Trong gia đình có ai?",
        "Who likes tea?": "Ai thích trà?",
        "Who lives together?": "Ai sống cùng nhau?",
        "Who looks at the computer?": "Ai nhìn vào máy tính?",
        "Who speaks Chinese?": "Ai nói tiếng Trung?",
        "Why does the person go?": "Tại sao người đó đi?",
        "Chinese date order is month before day.": "Thứ tự ngày tháng trong tiếng Trung là tháng trước ngày.",
        "This final passage combines weather, people, school, study, and emotion using HSK1 vocabulary.": "Đoạn đọc cuối cùng này kết hợp thời tiết, con người, trường học, việc học và cảm xúc bằng từ vựng HSK1.",
        "A movie": "Một bộ phim",
        "Also a teacher": "Cũng là giáo viên",
        "Buy things": "Mua đồ",
        "Her daughter": "Con gái của cô ấy",
        "My daughter": "Con gái tôi",
        "The movie": "Bộ phim đó",
        "Three yuan": "Ba tệ",
        "To buy things": "Để mua đồ",
        "Whether you can write": "Có thể viết được hay không",
        # HSK1 reading-passage grammar explanations that quote a Chinese
        # word/phrase inline (kept unchanged) alongside English commentary
        # (translated below).
        "Both sentences use 在学校 to show location.": "Cả hai câu đều dùng 在学校 để chỉ địa điểm.",
        "The passage introduces 我是学生 and asks a yes-no question with 吗.": "Đoạn văn giới thiệu 我是学生 và đặt câu hỏi có/không với 吗.",
        "The structure A 是 B identifies each person's role.": "Cấu trúc A 是 B xác định vai trò của mỗi người.",
        "The verb 喝 is followed by different drinks.": "Động từ 喝 được theo sau bởi các loại đồ uống khác nhau.",
        "一点儿 means a little amount.": "一点儿 nghĩa là một chút.",
        "上 and 里 show location.": "上 và 里 chỉ vị trí.",
        "不去学校 means the teacher does not go to school.": "不去学校 nghĩa là giáo viên không đến trường.",
        "不是 negates identity, and the next sentence gives the correct identity.": "不是 phủ định danh tính, và câu tiếp theo đưa ra danh tính đúng.",
        "中午 sets the time; 也 adds another action.": "中午 nêu thời gian; 也 thêm một hành động khác.",
        "中国人 means Chinese person, and 会说汉语 means can speak Chinese.": "中国人 nghĩa là người Trung Quốc, và 会说汉语 nghĩa là biết nói tiếng Trung.",
        "也 comes before 是 to mean also is.": "也 đứng trước 是 để nói cũng là.",
        "也喜欢 shows that mom has the same preference.": "也喜欢 cho thấy mẹ cũng có cùng sở thích.",
        "也很漂亮 adds another description of the cat.": "也很漂亮 thêm một miêu tả khác về con mèo.",
        "也很高兴 adds a second adjective.": "也很高兴 thêm một tính từ thứ hai.",
        "也说再见 shows the students repeat the same farewell.": "也说再见 cho thấy các học sinh cũng nói lời tạm biệt tương tự.",
        "了 shows a new situation: the store has opened.": "了 cho thấy một tình huống mới: cửa hàng đã mở cửa.",
        "什么 asks for the identity of the thing.": "什么 dùng để hỏi đó là vật gì.",
        "今天 and 明天 mark two different days.": "今天 và 明天 đánh dấu hai ngày khác nhau.",
        "住在中国 gives the place of living.": "住在中国 cho biết nơi sinh sống.",
        "你好吗 is a simple greeting question.": "你好吗 là một câu hỏi chào hỏi đơn giản.",
        "几个人 asks for a small number of people.": "几个人 dùng để hỏi một số lượng người nhỏ.",
        "前面 and 后面 contrast two locations.": "前面 và 后面 đối lập hai vị trí.",
        "前面 and 后面 describe relative position.": "前面 và 后面 mô tả vị trí tương đối.",
        "去商店买 shows purpose: going to the store to buy something.": "去商店买 cho biết mục đích: đến cửa hàng để mua thứ gì đó.",
        "去商店买东西 shows destination and purpose.": "去商店买东西 cho biết điểm đến và mục đích.",
        "叫什么名字 is the standard HSK1 pattern for asking a name.": "叫什么名字 là mẫu câu HSK1 chuẩn để hỏi tên.",
        "同学 means classmate, and 都 applies to all of 我们.": "同学 nghĩa là bạn học, và 都 áp dụng cho tất cả 我们.",
        "听老师说话 means listen to the teacher speak.": "听老师说话 nghĩa là nghe giáo viên nói.",
        "哪个 asks which one from a group.": "哪个 dùng để hỏi cái nào trong một nhóm.",
        "喂 is used when answering or starting a phone call.": "喂 được dùng khi trả lời hoặc bắt đầu một cuộc gọi điện thoại.",
        "喜欢 can be followed by a verb phrase.": "喜欢 có thể được theo sau bởi một cụm động từ.",
        "回北京 means return to Beijing.": "回北京 nghĩa là trở về Bắc Kinh.",
        "回家 means return/go home, and 也 shows the teacher does the same.": "回家 nghĩa là về nhà, và 也 cho thấy giáo viên cũng làm như vậy.",
        "在 + place + 工作 shows where someone works.": "在 + địa điểm + 工作 cho biết ai đó làm việc ở đâu.",
        "在北京 shows location, and 很大 describes Beijing.": "在北京 cho biết địa điểm, và 很大 miêu tả Bắc Kinh.",
        "在医院 gives the doctor's location, and 去医院 shows mom's destination.": "在医院 cho biết vị trí của bác sĩ, và 去医院 cho biết điểm đến của mẹ.",
        "在哪儿 asks for location.": "在哪儿 dùng để hỏi địa điểm.",
        "在学校 comes before the action 看书.": "在学校 đứng trước hành động 看书.",
        "在家 shows where the action 做工作 happens.": "在家 cho biết hành động 做工作 diễn ra ở đâu.",
        "坐出租车 means take a taxi, and 去医院 gives the destination.": "坐出租车 nghĩa là đi taxi, và 去医院 cho biết điểm đến.",
        "坐在椅子上 describes sitting on the chair.": "坐在椅子上 miêu tả việc ngồi trên ghế.",
        "坐飞机去北京 means take a plane to Beijing.": "坐飞机去北京 nghĩa là đi máy bay đến Bắc Kinh.",
        "多大 asks age, and 岁 marks years old.": "多大 dùng để hỏi tuổi, và 岁 đánh dấu đơn vị tuổi.",
        "多少钱 asks price, and 三块 gives the spoken price.": "多少钱 dùng để hỏi giá, và 三块 cho biết giá được nói ra.",
        "太...了 expresses a strong degree; 不喝 is negative.": "太...了 diễn tả mức độ mạnh; 不喝 là dạng phủ định.",
        "女儿 is identified as a student, then her location is given.": "女儿 được xác định là học sinh, sau đó vị trí của cô được nêu ra.",
        "她是老师 identifies her role, and 老师好 is a greeting to a teacher.": "她是老师 xác định vai trò của cô ấy, và 老师好 là lời chào dành cho giáo viên.",
        "很 + 多 means many, while 不多 means not many.": "很 + 多 nghĩa là nhiều, còn 不多 nghĩa là không nhiều.",
        "很大 and 很小 describe size.": "很大 và 很小 miêu tả kích thước.",
        "很好 describes the weather positively.": "很好 miêu tả thời tiết theo hướng tích cực.",
        "很好 evaluates the movie positively.": "很好 đánh giá bộ phim theo hướng tích cực.",
        "很热 describes the weather, and the second sentence gives the action.": "很热 miêu tả thời tiết, và câu thứ hai nêu hành động.",
        "怎么样 asks about condition, and 很好 answers positively.": "怎么样 dùng để hỏi tình trạng, và 很好 trả lời theo hướng tích cực.",
        "怎么样 asks how something is.": "怎么样 dùng để hỏi một điều gì đó như thế nào.",
        "想 + verb expresses wanting to do something.": "想 + động từ diễn tả mong muốn làm điều gì đó.",
        "想睡觉 means want to sleep.": "想睡觉 nghĩa là muốn ngủ.",
        "我家有 introduces the people in the family.": "我家有 giới thiệu những người trong gia đình.",
        "我的朋友 shows possession, and 都 means all.": "我的朋友 cho biết sở hữu, và 都 nghĩa là tất cả.",
        "明天 gives future time, and 在家 gives location.": "明天 cho biết thời gian trong tương lai, và 在家 cho biết địa điểm.",
        "星期 plus a number gives the weekday.": "星期 cộng với một con số cho biết thứ trong tuần.",
        "月 marks the month, and 很热 describes the weather.": "月 đánh dấu tháng, và 很热 miêu tả thời tiết.",
        "有 expresses possession, and 吗 turns the second sentence into a question.": "有 diễn tả sự sở hữu, và 吗 biến câu thứ hai thành câu hỏi.",
        "有 is repeated as a short positive answer.": "有 được lặp lại như một câu trả lời khẳng định ngắn.",
        "来学校 means come to school.": "来学校 nghĩa là đến trường.",
        "桌子上有 introduces what is on the table.": "桌子上有 giới thiệu những gì có trên bàn.",
        "没有 is the negative form of 有.": "没有 là dạng phủ định của 有.",
        "没有 negates existence, and the second sentence gives the replacement drink.": "没有 phủ định sự tồn tại, và câu thứ hai đưa ra loại đồ uống thay thế.",
        "没有钱 explains why the person does not buy things.": "没有钱 giải thích lý do người đó không mua đồ.",
        "狗 is the subject of the second sentence and is described with 很大.": "狗 là chủ ngữ của câu thứ hai và được miêu tả bằng 很大.",
        "现在 sets the present time for both sentences.": "现在 xác lập thời điểm hiện tại cho cả hai câu.",
        "看电视 means watch TV; 也 shows dad does the same.": "看电视 nghĩa là xem TV; 也 cho thấy bố cũng làm như vậy.",
        "看见 means see, and 学校前面 gives the location.": "看见 nghĩa là nhìn thấy, và 学校前面 cho biết địa điểm.",
        "看见 means to see, and 很高兴 describes feeling.": "看见 nghĩa là nhìn thấy, và 很高兴 miêu tả cảm xúc.",
        "能来 means be able to come.": "能来 nghĩa là có thể đến.",
        "菜 means dish/food, and 这个菜 identifies a specific dish.": "菜 nghĩa là món ăn, và 这个菜 xác định một món ăn cụ thể.",
        "认识 means to know or be acquainted with someone.": "认识 nghĩa là biết hoặc quen biết ai đó.",
        "请 makes the command polite.": "请 làm cho câu mệnh lệnh trở nên lịch sự.",
        "谁 asks about a person.": "谁 dùng để hỏi về một người.",
        "谢谢 and 不客气 form a basic polite exchange.": "谢谢 và 不客气 tạo thành một cặp trao đổi lịch sự cơ bản.",
        "这 and 那 point to two things, and 也 shows the second is also a book.": "这 và 那 chỉ vào hai vật, và 也 cho thấy vật thứ hai cũng là một quyển sách.",
        "这个电脑 is described with 很好.": "这个电脑 được miêu tả bằng 很好.",
        "都 applies to both 先生 and 小姐.": "都 áp dụng cho cả 先生 và 小姐.",
        "都 applies to both 我 and 朋友.": "都 áp dụng cho cả 我 và 朋友.",
        "都 means all members of the listed group are at home.": "都 nghĩa là tất cả thành viên trong nhóm được liệt kê đều ở nhà.",
        "饭店 can mean hotel/restaurant in beginner HSK context; here 住饭店 means stay at a hotel.": "饭店 trong ngữ cảnh HSK sơ cấp có thể nghĩa là khách sạn/nhà hàng; ở đây 住饭店 nghĩa là ở khách sạn.",
        # Remaining lesson/reading titles and learning objectives found by the
        # i18n audit to have identical (untranslated) EN/VI values.
        "My First Class": "Buổi học đầu tiên của tôi",
        "Making a Weekend Plan": "Lập kế hoạch cuối tuần",
        "Use time words before verbs.": "Dùng từ chỉ thời gian trước động từ.",
        "Ask and answer where and when to meet.": "Hỏi và trả lời về nơi và thời gian gặp mặt.",
        "Efficiency Is Not Only Resources": "Hiệu quả không chỉ là nguồn lực",
        "Use simple person words in short sentences": "Dùng từ chỉ người đơn giản trong câu ngắn",
        "Identify person and role information": "Xác định thông tin về người và vai trò",
        "Ask a person's name": "Hỏi tên một người",
        "Answer with a name": "Trả lời bằng tên",
        "Review identity and name patterns": "Ôn tập mẫu câu về danh tính và tên gọi",
        "Ask whether an action happened": "Hỏi xem một hành động đã xảy ra chưa",
        "Read a simple weekend plan": "Đọc một kế hoạch cuối tuần đơn giản",
        "Identify time and place": "Xác định thời gian và địa điểm",
        "Understand a short phone plan": "Hiểu một cuộc hẹn ngắn qua điện thoại",
        "Compare two people or things": "So sánh hai người hoặc hai vật",
        "Review completed actions and comparisons": "Ôn tập hành động đã hoàn thành và so sánh",
        "Read a service problem": "Đọc một vấn đề về dịch vụ",
        "Explain causes and solutions": "Giải thích nguyên nhân và giải pháp",
        "Name social and environmental issues": "Nêu tên các vấn đề xã hội và môi trường",
        "Express sufficient and concessive conditions": "Diễn đạt điều kiện đủ và nhượng bộ",
        "Discuss habits and plans": "Thảo luận về thói quen và kế hoạch",
        "Review contrast and condition structures": "Ôn tập cấu trúc tương phản và điều kiện",
        "Discuss reports and viewpoints": "Thảo luận báo cáo và quan điểm",
        "Identify claim and supporting reason": "Xác định luận điểm và lý do hỗ trợ",
        "Distinguish experience and opinion": "Phân biệt trải nghiệm và ý kiến",
        "Correct an assumption": "Sửa một giả định sai",
        "Compare online and offline study": "So sánh học trực tuyến và học trực tiếp",
        "Review opinion and debate vocabulary": "Ôn tập từ vựng nêu ý kiến và tranh luận",
        "Listen for stance and evidence": "Nghe để xác định lập trường và bằng chứng",
        "Identify thesis, evidence, and implication": "Xác định luận điểm, bằng chứng và hàm ý",
        "Review abstract reading and listening strategies": "Ôn tập chiến lược đọc và nghe trừu tượng",
        "write a qualified analytical response": "viết một bài phân tích có luận cứ rõ ràng",
        # HSK1 reading-passage multiple-choice answer options.
        "My doctor": "Bác sĩ của tôi",
        "My dad": "Bố tôi",
        "A chair": "Một cái ghế",
        "The price": "Giá tiền",
        "A movie only": "Chỉ xem phim",
        "Only a doctor": "Chỉ có bác sĩ",
        "Price of apples": "Giá táo",
        "Her teacher": "Giáo viên của cô ấy",
        "Her doctor": "Bác sĩ của cô ấy",
        "Her friend": "Bạn của cô ấy",
        "It has no money": "Không có tiền",
        "In Beijing": "Ở Bắc Kinh",
        # Conversation-quiz prompts/explanations/image-keywords found by a
        # full database scan to still be identical or partially untranslated.
        "What is his job?": "Công việc của anh ấy là gì?",
        "What is the advice?": "Lời khuyên là gì?",
        "What is the guest's surname?": "Họ của khách là gì?",
        "What is the speaker asking?": "Người nói đang hỏi gì?",
        "What price do you hear?": "Bạn nghe thấy giá bao nhiêu?",
        "What should the patient do?": "Bệnh nhân nên làm gì?",
        "What should the student write?": "Học sinh nên viết gì?",
        "What will the customer do?": "Khách hàng sẽ làm gì?",
        "What will the speaker bring?": "Người nói sẽ mang theo gì?",
        "When does it start?": "Khi nào bắt đầu?",
        "When is the person free?": "Khi nào người đó rảnh?",
        "When should it be handed in?": "Khi nào cần nộp?",
        "Which two items are requested?": "Hai món đồ nào được yêu cầu?",
        "school gate": "cổng trường",
        "hotel room key card": "thẻ phòng khách sạn",
        "Type the Hanzi for 'to buy'.": "Nhập chữ Hán cho nghĩa 'mua'.",
        "同事 means colleague.": "同事 nghĩa là đồng nghiệp.",
        "Choose the correct order.": "Chọn thứ tự đúng.",
        "Choose the natural question for asking a name.": "Chọn câu hỏi tự nhiên để hỏi tên.",
        "How is the weather today?": "Hôm nay thời tiết thế nào?",
        "How much are these noodles?": "Mì này giá bao nhiêu?",
        "How long does it take on foot?": "Đi bộ mất bao lâu?",
        "How many people are in the speaker's family?": "Gia đình người nói có mấy người?",
        "How much is the clothing item?": "Món quần áo đó giá bao nhiêu?",
        "The image shows a doctor.": "Hình ảnh cho thấy một bác sĩ.",
        "The image shows a hotel front desk.": "Hình ảnh cho thấy quầy lễ tân khách sạn.",
        "The image shows a movie setting.": "Hình ảnh cho thấy bối cảnh một bộ phim.",
        "The image shows a park.": "Hình ảnh cho thấy một công viên.",
        "The image shows a passport.": "Hình ảnh cho thấy một hộ chiếu.",
        "The image shows a room card.": "Hình ảnh cho thấy một thẻ phòng.",
        "The image shows a school gate.": "Hình ảnh cho thấy cổng trường.",
        "The image shows a subway station sign.": "Hình ảnh cho thấy biển ga tàu điện ngầm.",
        "The image shows a suitcase.": "Hình ảnh cho thấy một vali.",
        "The image shows a teacher.": "Hình ảnh cho thấy một giáo viên.",
        "The image shows a train station.": "Hình ảnh cho thấy một nhà ga.",
        "The image shows an office.": "Hình ảnh cho thấy một văn phòng.",
        "The image shows beef noodles.": "Hình ảnh cho thấy mì bò.",
        "The image shows clothing.": "Hình ảnh cho thấy quần áo.",
        "The image shows documents.": "Hình ảnh cho thấy tài liệu.",
        "The image shows four people.": "Hình ảnh cho thấy bốn người.",
        "The image shows homework.": "Hình ảnh cho thấy bài tập về nhà.",
        "The image shows medicine.": "Hình ảnh cho thấy thuốc.",
        "The image shows rain.": "Hình ảnh cho thấy trời mưa.",
        "The pattern connects two contrasting ideas.": "Mẫu câu này nối hai ý tương phản.",
        "The pattern rejects one idea and replaces it with a better explanation.": "Mẫu câu này bác bỏ một ý và thay bằng cách giải thích tốt hơn.",
        "They discuss going to the park tomorrow.": "Họ bàn về việc đi công viên vào ngày mai.",
        "Time comes before the verb phrase.": "Từ chỉ thời gian đứng trước cụm động từ.",
        "Type the polite Chinese pronoun for 'you'.": "Nhập đại từ tiếng Trung lịch sự cho 'bạn'.",
        "What are the students studying today?": "Hôm nay học sinh đang học gì?",
        "What do the friends plan to do?": "Nhóm bạn dự định làm gì?",
        "What does the customer order to eat?": "Khách hàng gọi món gì để ăn?",
        "What does the doctor advise?": "Bác sĩ khuyên điều gì?",
        "What is the father's job?": "Công việc của người bố là gì?",
        "What symptoms does the patient have?": "Bệnh nhân có triệu chứng gì?",
        "What will the friends do tomorrow?": "Ngày mai nhóm bạn sẽ làm gì?",
        "Where does the tourist want to go?": "Du khách muốn đi đâu?",
        "Where is the fitting room?": "Phòng thử đồ ở đâu?",
        "Where is the meeting?": "Cuộc họp ở đâu?",
        "Which phrase is most polite for asking a question?": "Cụm từ nào lịch sự nhất để đặt câu hỏi?",
        "Which phrase means 'I want to go'?": "Cụm từ nào có nghĩa là 'tôi muốn đi'?",
        "Which phrase means 'a little smaller'?": "Cụm từ nào có nghĩa là 'nhỏ hơn một chút'?",
        "Which phrase means 'a little'?": "Cụm từ nào có nghĩa là 'một chút'?",
        "Which phrase means 'after ten o'clock'?": "Cụm từ nào có nghĩa là 'sau mười giờ'?",
        "Which structure asks age?": "Cấu trúc nào dùng để hỏi tuổi?",
        "Which structure gives direction?": "Cấu trúc nào chỉ hướng?",
        "Which word asks 'what'?": "Từ nào dùng để hỏi 'cái gì'?",
        "Which word means 'then'?": "Từ nào có nghĩa là 'thì/rồi'?",
    }
)


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


def _translate_title_phrase(phrase: str) -> str:
    return TOPIC_TITLE_VI.get(phrase) or TITLE_PHRASE_VI.get(phrase) or phrase


def _lesson_title_translations(title: str, lesson_type: str | None = None) -> dict[str, str]:
    generated_match = re.match(
        r"^(HSK\d+) (Core Lesson|Vocabulary|Grammar|Listening|Reading|Writing) (\d{2}): (.+)$",
        title,
    )
    if generated_match:
        hsk, type_label, number, topic = generated_match.groups()
        type_vi = TYPE_TITLES_VI.get(lesson_type or "", type_label)
        return _translations(title, f"{hsk} {type_vi} {number}: {_translate_title_phrase(topic)}")

    hsk_match = re.match(r"^(HSK\d+) ([^:]+): (.+)$", title)
    if hsk_match:
        hsk, type_label, phrase = hsk_match.groups()
        type_vi = TYPE_TITLES_VI.get(lesson_type or "", type_label)
        return _translations(title, f"{hsk} {type_vi}: {_translate_title_phrase(phrase)}")

    reading_match = re.match(r"^Reading (\d{3}): (.+)$", title)
    if reading_match:
        number, phrase = reading_match.groups()
        return _translations(title, f"Bài đọc {number}: {_translate_title_phrase(phrase)}")

    return _translations(title, _translate_title_phrase(title))


def _lesson_description_translations(
    description: str | None,
    lesson_type: str,
    hsk_level: int,
    title_translations: dict[str, str],
) -> dict[str, str]:
    if not description:
        return {}

    type_en = TYPE_TITLES.get(lesson_type, lesson_type.title())
    type_vi = TYPE_TITLES_VI.get(lesson_type, type_en)
    vi_title = title_translations.get("vi", "")
    return _translations(
        description,
        f"{type_vi} HSK {hsk_level}: {vi_title.split(': ', 1)[-1] if vi_title else description}.",
    )


def _has_vietnamese_letters(text: str) -> bool:
    return bool(re.search(r"[À-ỹ]", text))


_ENGLISH_FUNCTION_WORDS_RE = re.compile(
    r"\b(the|a|an|is|are|was|were|am|do|does|did|will|would|can|could|should|"
    r"shall|must|may|might|has|have|had|and|or|but|if|when|where|what|how|who|"
    r"whom|whose|which|why|at|in|on|to|of|for|with|before|after|behind|front|"
    r"this|that|these|those|it|its|he|she|they|we|you|your|my|his|her|their|"
    r"our|not|no|yes|home|gate|room|card|meeting|school|hospital|hotel|"
    r"airport|office|restaurant|teacher|student|doctor|weather|morning|"
    r"afternoon|tonight|money|price|name|time|water|table|chair|chairs|"
    r"computer|documents?|medicine|luggage|passport|ticket|suitcase|receipt|"
    r"shoes|clothes|correct|paid|twice|nearby|cold|expensive|old)\b",
    re.IGNORECASE,
)

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def _maybe_translate_subject_vi(text: str) -> str:
    """Translate a captured sentence subject unless it is (or contains) Chinese
    content, which must stay untouched (e.g. grammar explanations quoting a
    Chinese word/phrase as the subject)."""
    if _CJK_RE.search(text):
        return text
    return _translate_fragment_vi(text)


def _translate_fragment_vi(text: str) -> str:
    stripped = text.strip().strip("'\"")
    bare = stripped.rstrip(".?")
    lower = bare.lower()
    if stripped in EN_TEXT_VI:
        return EN_TEXT_VI[stripped]
    if bare in EN_TEXT_VI:
        return EN_TEXT_VI[bare]
    if stripped in TITLE_PHRASE_VI:
        return TITLE_PHRASE_VI[stripped]
    if lower in EN_TERM_VI:
        return EN_TERM_VI[lower]

    word_map = {
        key: value
        for key, value in EN_TERM_VI.items()
        if re.fullmatch(r"[a-z]+", key)
    }
    substituted = re.sub(
        r"[A-Za-z]+",
        lambda match: word_map.get(match.group(0).lower(), match.group(0)),
        stripped,
    )
    if substituted == stripped:
        # Nothing matched at all; there is no dictionary entry for this phrase.
        return stripped
    # Word-by-word substitution can leave common English function words next to
    # the newly-translated Vietnamese words (e.g. "At the trường học gate"),
    # producing a mixed-language string. That is strictly worse than a single
    # consistent language, so bail out to the untranslated original phrase
    # rather than surface a half-translated result; callers should add a full
    # phrase entry to `EN_TEXT_VI` once this fires.
    if _ENGLISH_FUNCTION_WORDS_RE.search(substituted):
        return stripped
    return substituted


def _translate_grammar_title_vi(text: str) -> str:
    grammar_replacements = {
        "Subject": "Chủ ngữ",
        "Object": "tân ngữ",
        "Verb": "động từ",
        "Name": "tên",
        "Adjective": "tính từ",
        "Time Before Action": "Thời gian đứng trước hành động",
        "Time": "thời gian",
        "Statement": "Câu trần thuật",
        "question": "câu hỏi",
        "sentence": "câu",
        "future/intention": "tương lai/dự định",
        "completed action": "hành động đã hoàn thành",
        "negated identity": "nhận diện phủ định",
        "identity statements": "câu nhận diện",
        "measure word": "lượng từ",
        "noun": "danh từ",
        "direction": "hướng",
        "parallel development": "diễn biến song song",
        "conclusion": "kết luận",
        "restatement": "diễn đạt lại",
    }
    translated = text
    for source, target in sorted(grammar_replacements.items(), key=lambda item: len(item[0]), reverse=True):
        translated = re.sub(rf"\b{re.escape(source)}\b", target, translated)
    return translated


def _translate_native_text(text: str | None) -> str:
    if not text:
        return ""
    if "\n" in text:
        return "\n".join(_translate_native_text(line) for line in text.splitlines())
    if text.startswith("Audio: "):
        return f"Âm thanh: {text.removeprefix('Audio: ')}"
    if text.startswith("Image: "):
        return f"Hình ảnh: {_translate_fragment_vi(text.removeprefix('Image: '))}"
    if text.startswith("Tokens: "):
        return f"Từ cho sẵn: {text.removeprefix('Tokens: ')}"
    if text in EN_TEXT_VI:
        return EN_TEXT_VI[text]
    if text in TITLE_PHRASE_VI:
        return TITLE_PHRASE_VI[text]
    replacements = {
        "Choose the best meaning.": "Chọn nghĩa phù hợp nhất.",
        "Choose the matching Chinese word.": "Chọn từ tiếng Trung phù hợp.",
        "Choose the matching phrase.": "Chọn cụm phù hợp.",
        "Choose the matching word.": "Chọn từ phù hợp.",
        "Arrange the words into a sentence.": "Sắp xếp các từ thành câu.",
        "Arrange the words into a question.": "Sắp xếp các từ thành câu hỏi.",
        "Arrange the words into a location question.": "Sắp xếp các từ thành câu hỏi vị trí.",
        "Arrange the words into a permission question.": "Sắp xếp các từ thành câu hỏi xin phép.",
        "Arrange the words into a price question.": "Sắp xếp các từ thành câu hỏi giá tiền.",
        "What is the main topic of this lesson?": "Chủ đề chính của bài này là gì?",
        "Reading": "Đọc hiểu",
        "Listening": "Nghe",
        "Writing": "Viết",
        "Grammar": "Ngữ pháp",
        "Vocabulary": "Từ vựng",
        "Practice": "Luyện tập",
        "Correct": "Đúng",
        "No answer": "Chưa trả lời",
        "Are there many teachers?": "Có nhiều giáo viên không?",
        "Can the speaker come?": "Người nói có thể đến không?",
        "Do they go to the restaurant today?": "Hôm nay họ có đi nhà hàng không?",
        "Does the person drink it?": "Người đó có uống nó không?",
        "Does the speaker know him?": "Người nói có biết anh ấy không?",
        "Does the teacher have a book?": "Giáo viên có sách không?",
        "How do they feel?": "Họ cảm thấy thế nào?",
        "How does the person feel?": "Người đó cảm thấy thế nào?",
        "How does the teacher feel?": "Giáo viên cảm thấy thế nào?",
        "How else does the daughter feel?": "Con gái còn cảm thấy thế nào?",
        "How much is it?": "Giá bao nhiêu?",
        "How much are the noodles?": "Mì giá bao nhiêu?",
        "How old is the speaker?": "Người nói bao nhiêu tuổi?",
        "Is it far?": "Nó có xa không?",
        "Is the son a teacher?": "Người con trai có phải giáo viên không?",
        "What is asked?": "Đang hỏi điều gì?",
        "What is being asked?": "Đang hỏi điều gì?",
        "What is being bought?": "Đang mua gì?",
        "What is asked about?": "Đang hỏi về điều gì?",
        "What date is today?": "Hôm nay là ngày mấy?",
        "What date is tomorrow?": "Ngày mai là ngày mấy?",
        "What day is mentioned?": "Nhắc đến ngày nào?",
        "What day is today?": "Hôm nay là thứ mấy?",
        "What day is tomorrow?": "Ngày mai là thứ mấy?",
        "What direction is given?": "Chỉ hướng nào?",
        "What does the question ask?": "Câu hỏi hỏi gì?",
        "What does the speaker ask?": "Người nói hỏi gì?",
        "What does the speaker say about today?": "Người nói nói gì về hôm nay?",
        "What does the staff ask to see?": "Nhân viên yêu cầu xem gì?",
        "What does 不客气 mean?": "不客气 nghĩa là gì?",
        "What does 哪个 mean?": "哪个 nghĩa là gì?",
        "What does 家里 mean here?": "家里 ở đây nghĩa là gì?",
        "What does 有 show?": "有 biểu thị điều gì?",
        "What does 都 mean here?": "都 ở đây nghĩa là gì?",
        "What floor is the room on?": "Phòng ở tầng mấy?",
        "What fruit is liked?": "Thích loại trái cây nào?",
        "What happened to the store?": "Cửa hàng đã xảy ra chuyện gì?",
        "Who is a student?": "Ai là học sinh?",
    }
    if text in replacements:
        return replacements[text]

    translated_grammar = _translate_grammar_title_vi(text)
    if translated_grammar != text and not _ENGLISH_FUNCTION_WORDS_RE.search(translated_grammar):
        return translated_grammar

    for prefix, translated_prefix in (
        ("Choose the meaning of ", "Chọn nghĩa của "),
        ("Complete the sentence: ", "Hoàn thành câu: "),
        ("Complete the question: ", "Hoàn thành câu hỏi: "),
        ("Complete: ", "Hoàn thành: "),
        ("Translate to Chinese: ", "Dịch sang tiếng Trung: "),
        ("Translate to English: ", "Dịch sang tiếng Anh: "),
        ("Translate to Vietnamese: ", "Dịch sang tiếng Việt: "),
        ("Type the Hanzi for ", "Nhập chữ Hán cho nghĩa "),
    ):
        if text.startswith(prefix):
            return translated_prefix + _translate_fragment_vi(text.removeprefix(prefix))

    pattern_translators = (
        (r"^What does (.+) mean\?$", lambda m: f"{_translate_fragment_vi(m.group(1))} nghĩa là gì?"),
        (r"^What is (.+)\?$", lambda m: f"{_translate_fragment_vi(m.group(1))} là gì?"),
        (r"^Who is (.+)\?$", lambda m: f"{_translate_fragment_vi(m.group(1))} là ai?"),
        (r"^Where is (.+)\?$", lambda m: f"{_translate_fragment_vi(m.group(1))} ở đâu?"),
        (r"^How is (.+)\?$", lambda m: f"{_translate_fragment_vi(m.group(1))} như thế nào?"),
        (r"^How much (?:is|are) (.+)\?$", lambda m: f"{_translate_fragment_vi(m.group(1))} giá bao nhiêu?"),
        (r"^How many people are in (.+)\?$", lambda m: f"{_translate_fragment_vi(m.group(1))} có mấy người?"),
        (r"^How long does it take (.+)\?$", lambda m: f"Mất bao lâu { _translate_fragment_vi(m.group(1)) }?"),
        (r"^What can (.+) do\?$", lambda m: f"{_translate_fragment_vi(m.group(1))} có thể làm gì?"),
        (r"^What can (.+) speak\?$", lambda m: f"{_translate_fragment_vi(m.group(1))} nói được gì?"),
        (r"^What are (.+)\?$", lambda m: f"{_translate_fragment_vi(m.group(1))} là gì?"),
        (r"^What are (.+) doing\?$", lambda m: f"{_translate_fragment_vi(m.group(1))} đang làm gì?"),
        (r"^What did (.+) do yesterday\?$", lambda m: f"Hôm qua {_translate_fragment_vi(m.group(1))} đã làm gì?"),
        (r"^What do (.+) (?:eat|drink|watch|study|like)\?$", lambda m: f"{_translate_fragment_vi(m.group(1))} {_translate_fragment_vi(m.group(0).split()[-1].rstrip('?'))} gì?"),
        (r"^What do (.+) have\?$", lambda m: f"{_translate_fragment_vi(m.group(1))} có gì?"),
        (r"^What does (.+) (?:eat|drink|watch|study|write|buy|like|order|want)\?$", lambda m: f"{_translate_fragment_vi(m.group(1))} {_translate_fragment_vi(m.group(0).split()[-1].rstrip('?'))} gì?"),
        (r"^What does (.+) ask\?$", lambda m: f"{_translate_fragment_vi(m.group(1))} hỏi gì?"),
        (r"^What does (.+) say\?$", lambda m: f"{_translate_fragment_vi(m.group(1))} nói gì?"),
        (r"^What does (.+) do\?$", lambda m: f"{_translate_fragment_vi(m.group(1))} làm gì?"),
        (r"^The speaker says: (.+)\.?$", lambda m: f"Người nói nói: {m.group(1)}."),
        (r"^The passage introduces (.+)\.?$", lambda m: f"Đoạn đọc giới thiệu {_maybe_translate_subject_vi(m.group(1))}."),
        (r"^(.+) asks (.+)\.?$", lambda m: f"{_maybe_translate_subject_vi(m.group(1))} dùng để hỏi {_translate_fragment_vi(m.group(2))}."),
        (r"^(.+) means (.+)\.?$", lambda m: f"{_maybe_translate_subject_vi(m.group(1))} nghĩa là {_translate_fragment_vi(m.group(2))}."),
        (r"^(.+) shows (.+)\.?$", lambda m: f"{_maybe_translate_subject_vi(m.group(1))} biểu thị {_translate_fragment_vi(m.group(2))}."),
        (r"^(.+) identifies (.+)\.?$", lambda m: f"{_maybe_translate_subject_vi(m.group(1))} xác định {_translate_fragment_vi(m.group(2))}."),
    )
    for pattern, translator in pattern_translators:
        match = re.match(pattern, text)
        if match:
            candidate = translator(match)
            # Skip patterns that leave a broken mixed-language remainder (a
            # captured group with no dictionary translation); try the next
            # pattern instead of surfacing half-translated text.
            if not _ENGLISH_FUNCTION_WORDS_RE.search(candidate):
                return candidate

    fragment_translation = _translate_fragment_vi(text)
    if fragment_translation != text:
        return fragment_translation

    return text


def _translate_native_text_en(text: str | None) -> str:
    if not text:
        return ""
    if "\n" in text:
        return "\n".join(_translate_native_text_en(line) for line in text.splitlines())
    if text in VI_TEXT_EN:
        return VI_TEXT_EN[text]
    inverse_titles = {value: key for key, value in TITLE_PHRASE_VI.items()}
    if text in inverse_titles:
        return inverse_titles[text]
    inverse_terms = {value: key for key, value in EN_TERM_VI.items()}
    if text.lower() in inverse_terms:
        return inverse_terms[text.lower()]
    for prefix, translated_prefix in (
        ("Sai: ", "Incorrect: "),
        ("Đúng: ", "Correct: "),
        ("Nghĩa: ", "Meaning: "),
        ("Câu đầy đủ: ", "Full sentence: "),
        ("Theo bài đọc, ", "According to the reading, "),
        ("Điền từ còn thiếu: ", "Fill in the missing word: "),
        ("Hoàn thành câu: ", "Complete the sentence: "),
        ("Nhập chữ Hán cho nghĩa: ", "Type the Chinese character for: "),
        ("Sắp xếp thành câu đúng rồi nhập lại.", "Put the words in the correct order and type the sentence."),
    ):
        if text.startswith(prefix):
            return translated_prefix + text.removeprefix(prefix)
    if _has_vietnamese_letters(text):
        return text
    return text


def _native_text_translations(text: str | None) -> dict[str, str]:
    if not text:
        return {}
    return _translations(_translate_native_text_en(text), _translate_native_text(text))


def _option_translations(options: list[str]) -> dict[str, list[str]]:
    return {
        "en": [_translate_native_text_en(option) for option in options],
        "vi": [_translate_native_text(option) for option in options],
    }


def _question_translation_payload(question: dict[str, Any]) -> dict[str, Any]:
    prompt = question.get("prompt", "")
    explanation = question.get("explanation", "")
    options = question.get("options") or []
    return {
        "prompt_translations": question.get("prompt_translations")
        or _native_text_translations(prompt),
        "options_translations": question.get("options_translations") or (_option_translations(options) if options else {}),
        "explanation_translations": question.get("explanation_translations")
        or _native_text_translations(explanation),
    }


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
            "category_translations": _native_text_translations(category) or _translations(category, category),
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
                "title_translations": _native_text_translations(title),
                "structure": structure,
                "explanation": usage or structure or title,
                "explanation_translations": _translations(usage_en or usage, usage_vi),
                "examples": [
                    {
                        **_chinese_entry(
                            str(example.get("hanzi", example.get("Chinese", "")) or ""),
                            str(example.get("pinyin", example.get("Pinyin", "")) or ""),
                            str(
                                example.get("meaning_vi", example.get("Vietnamese", ""))
                                or example.get("meaning_en", example.get("English", ""))
                                or ""
                            ),
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
        "learning_objective_translations": {
            "en": lesson.get("learning_objectives", []),
            "vi": [_translate_native_text(objective) for objective in lesson.get("learning_objectives", [])],
        },
    }

    focus = raw.get("focus")
    # Some quiz entries store a prerequisite lesson id (e.g. "HSK1-CON-002") in
    # `focus` instead of a human-readable summary; never surface a raw id as
    # on-screen overview text.
    if focus and not re.match(r"^[A-Z]+\d*-[A-Z]+-\d+$", focus):
        content["overview"] = focus
        content["overview_translations"] = _translations(
            _translate_native_text_en(focus),
            raw.get("focus_vi") or _translate_native_text(focus),
        )

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
            "title_translations": _lesson_title_translations(title, lesson_type),
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
            "task_translations": _translations(
                _translate_native_text_en(focus) if focus else "Listen and answer the checkpoint.",
                raw.get("focus_vi") or _translate_native_text(focus) if focus else "Nghe và trả lời câu kiểm tra.",
            ),
        }
        content["transcript"] = [text_entry]
    elif text_entry and lesson_type == "conversation":
        content["dialogue"] = {
            "title": title,
            "title_translations": _lesson_title_translations(title, lesson_type),
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
        content["passage_title_translations"] = _lesson_title_translations(title, lesson_type)
        content["passage"] = [text_entry]

    items = raw.get("items", [])
    item_texts = [item.get("text", "") for item in items if isinstance(item, dict) and item.get("text")]
    item_types = {item.get("type") for item in items if isinstance(item, dict)}
    if "pattern" in item_types:
        content["sentence_patterns"] = content.get("sentence_patterns", []) + [
            {
                "pattern": text,
                "meaning_vi": focus or "",
                "meaning_en": _translate_native_text_en(focus) if focus else "",
                "translations": _translations(_translate_native_text_en(focus) if focus else "", raw.get("focus_vi") or _translate_native_text(focus) if focus else ""),
            }
            for text in item_texts
        ]
    elif "activity" in item_types:
        content["speaking_tasks"] = item_texts
        content["speaking_task_translations"] = {"en": [_translate_native_text_en(item) for item in item_texts], "vi": [_translate_native_text(item) for item in item_texts]}
    elif "review_scope" in item_types:
        content["reading_tasks"] = item_texts
        content["reading_task_translations"] = {"en": [_translate_native_text_en(item) for item in item_texts], "vi": [_translate_native_text(item) for item in item_texts]}
    elif item_texts:
        content["reading_tasks"] = item_texts
        content["reading_task_translations"] = {"en": [_translate_native_text_en(item) for item in item_texts], "vi": [_translate_native_text(item) for item in item_texts]}

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
            prompt = question.get("question", "")
            options = question.get("options", [])
            explanation = passage.get("explanation", "")
            questions.append(
                {
                    "type": "multiple_choice",
                    "prompt": prompt,
                    "prompt_translations": _native_text_translations(prompt),
                    "options": options,
                    "options_translations": _option_translations(options),
                    "correct_answer": answer,
                    "explanation": explanation,
                    "explanation_translations": _native_text_translations(explanation),
                }
            )
            reading_questions.append(
                {
                    "question": prompt,
                    "question_translations": _native_text_translations(prompt),
                    "answer": answer,
                    "answer_translations": _native_text_translations(answer),
                    "explanation": explanation,
                    "explanation_translations": _native_text_translations(explanation),
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
                    "learning_objective_translations": {
                        "en": [
                            "Read a short HSK1 text with familiar words.",
                            "Answer simple comprehension questions.",
                        ],
                        "vi": [
                            "Đọc một đoạn HSK1 ngắn với các từ quen thuộc.",
                            "Trả lời các câu hỏi đọc hiểu đơn giản.",
                        ],
                    },
                    "vocabulary": [
                        _chinese_entry(word)
                        for word in passage.get("vocabulary_list", [])
                    ],
                    "passage_title": passage.get("title", ""),
                    "passage_title_translations": _lesson_title_translations(passage.get("title", ""), "reading"),
                    "passage": [
                        {
                            **_chinese_entry(
                                passage.get("chinese_text", ""),
                                passage.get("pinyin", ""),
                                passage.get("vietnamese_translation", "") or passage.get("english_translation", ""),
                            ),
                            "meaning_en": passage.get("english_translation", ""),
                            "meaning_vi": passage.get("vietnamese_translation", ""),
                            "translations": _translations(
                                passage.get("english_translation", ""),
                                passage.get("vietnamese_translation", ""),
                            ),
                        }
                    ],
                    "reading": {
                        "title": passage.get("title", ""),
                        "title_translations": _lesson_title_translations(passage.get("title", ""), "reading"),
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
                            "title_translations": _translations("Reading checkpoint", "Kiểm tra đọc"),
                            "exercise_type": "multiple_choice",
                            "skill": "reading",
                            "prompt": first_question["prompt"] if first_question else "What is the passage about?",
                            "prompt_translations": first_question.get("prompt_translations")
                            if first_question
                            else _translations("What is the passage about?", "Bài đọc nói về điều gì?"),
                            "options": first_question["options"] if first_question else ["Reading", "Listening", "Writing", "Grammar"],
                            "options_translations": first_question.get("options_translations")
                            if first_question
                            else _option_translations(["Reading", "Listening", "Writing", "Grammar"]),
                            "correct_answer": first_question["correct_answer"] if first_question else "Reading",
                            "hint": "Đọc lại câu chứa thông tin chính trong đoạn.",
                            "hint_translations": _translations(
                                "Read again the sentence that contains the main information.",
                                "Đọc lại câu chứa thông tin chính trong đoạn.",
                            ),
                            "explanation": passage.get("explanation", ""),
                            "explanation_translations": _native_text_translations(passage.get("explanation", "")),
                        },
                        {
                            "id": f"{source_id}-PRACTICE-KEYWORD",
                            "title": "Keyword recall",
                            "title_translations": _translations("Keyword recall", "Nhớ từ khóa"),
                            "exercise_type": "text_input",
                            "skill": "reading",
                            "prompt": "Nhập một từ/cụm xuất hiện trong bài đọc.",
                            "prompt_translations": _translations(
                                "Enter one word or phrase that appears in the reading.",
                                "Nhập một từ/cụm xuất hiện trong bài đọc.",
                            ),
                            "correct_answer": first_keyword,
                            "expected_answer": first_keyword,
                            "hint": "Xem lại danh sách từ vựng của passage.",
                            "hint_translations": _translations(
                                "Review the passage vocabulary list.",
                                "Xem lại danh sách từ vựng của bài đọc.",
                            ),
                            "explanation": f"{first_keyword} xuất hiện trong đoạn đọc này.",
                            "explanation_translations": _translations(
                                f"{first_keyword} appears in this passage.",
                                f"{first_keyword} xuất hiện trong đoạn đọc này.",
                            ),
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
        "category_translations": _translations(topic["title"], topic["vi"]),
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
    # `GRAMMAR_EXPLANATION_EN` gives the exact English translation of this
    # specific grammar point's `explanation`. Without it, every grammar point
    # fell back to one generic templated sentence that did not match the
    # actual (specific) Vietnamese explanation, so switching locale from vi to
    # en showed unrelated content for the same grammar point.
    explanation_en = GRAMMAR_EXPLANATION_EN.get(explanation) or (
        f"Use the pattern {structure} to build accurate HSK {level} sentences. "
        "Read the example aloud, then replace one key word."
    )
    return {
        "title": title,
        "title_translations": _native_text_translations(title) or _translations(title, title),
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
    meaning_en_by_vi = {meaning_vi: meaning_en for _, _, meaning_vi, meaning_en in LEVEL_WORDS[level]}
    vocabulary_options = _with_correct_option(str(w0["meaning"]), meanings)

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
            "options": vocabulary_options,
            "options_translations": {
                "en": [meaning_en_by_vi.get(option, option) for option in vocabulary_options],
                "vi": vocabulary_options,
            },
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
            "prompt": "Điền từ còn thiếu: 今天我们学习____。",
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
    meaning_en_by_vi = {meaning_vi: meaning_en for _, _, meaning_vi, meaning_en in LEVEL_WORDS[level]}
    grammar_titles = [item[0] for item in GRAMMAR_PATTERNS[level]]
    topic_titles = [item["title"] for item in TOPICS]
    vocab_options = _with_correct_option(str(word["meaning"]), all_meanings)
    grammar_options = _with_correct_option(str(grammar_point["title"]), grammar_titles)
    topic_options = _with_correct_option(topic["title"], topic_titles[lesson_number:] + topic_titles[:lesson_number])
    return [
        {
            "type": "multiple_choice",
            "prompt": f"{word['hanzi']} means...",
            "prompt_translations": _translations(
                f"What does {word['hanzi']} mean?",
                f"{word['hanzi']} nghĩa là gì?",
            ),
            "options": vocab_options,
            "options_translations": {
                "en": [meaning_en_by_vi.get(option, option) for option in vocab_options],
                "vi": vocab_options,
            },
            "correct_answer": str(word["meaning"]),
            "explanation": f"{word['hanzi']} ({word.get('pinyin', '')}) = {word['meaning']}.",
            "explanation_translations": _translations(
                f"{word['hanzi']} ({word.get('pinyin', '')}) means {word.get('meaning_en', word['meaning'])}.",
                f"{word['hanzi']} ({word.get('pinyin', '')}) nghĩa là {word['meaning']}.",
            ),
        },
        {
            "type": "multiple_choice",
            "prompt": f"Which grammar point is practiced in this {lesson_type} lesson?",
            "prompt_translations": _translations(
                f"Which grammar point is practiced in this {TYPE_TITLES.get(lesson_type, lesson_type)} lesson?",
                f"Bài {TYPE_TITLES_VI.get(lesson_type, lesson_type)} này luyện điểm ngữ pháp nào?",
            ),
            "options": grammar_options,
            "options_translations": {
                "en": grammar_options,
                "vi": grammar_options,
            },
            "correct_answer": str(grammar_point["title"]),
            "explanation": f"The lesson highlights: {grammar_point['structure']}.",
            "explanation_translations": _translations(
                f"The lesson highlights: {grammar_point['structure']}.",
                f"Bài học nhấn mạnh mẫu: {grammar_point['structure']}.",
            ),
        },
        {
            "type": "multiple_choice",
            "prompt": "What is the main topic of this lesson?",
            "prompt_translations": _translations(
                "What is the main topic of this lesson?",
                "Chủ đề chính của bài này là gì?",
            ),
            "options": topic_options,
            "options_translations": {
                "en": topic_options,
                "vi": [_translate_title_phrase(option) for option in topic_options],
            },
            "correct_answer": topic["title"],
            "explanation": f"The lesson title and tasks focus on {topic['title'].lower()}.",
            "explanation_translations": _translations(
                f"The lesson title and tasks focus on {topic['title'].lower()}.",
                f"Tiêu đề và nhiệm vụ của bài tập trung vào chủ đề {topic['vi']}.",
            ),
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
                    "category_translations": _translations(topic["title"], topic["vi"]),
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
        metadata = _question_translation_payload(question)
        exercises.append(
            {
                "id": f"{source_id}-FALLBACK-{index}",
                "title": f"{TYPE_TITLES.get(lesson_type, 'Lesson')} checkpoint",
                "title_translations": _native_text_translations(f"{TYPE_TITLES.get(lesson_type, 'Lesson')} checkpoint"),
                "exercise_type": exercise_type,
                "skill": lesson_type,
                "prompt": question.get("prompt", "Review the lesson and answer."),
                "prompt_translations": metadata.get("prompt_translations"),
                "options": question.get("options"),
                "options_translations": metadata.get("options_translations"),
                "correct_answer": question.get("correct_answer", ""),
                "expected_answer": question.get("correct_answer", ""),
                "hint": "Xem lại nội dung chính của bài trước khi trả lời.",
                "hint_translations": _translations(
                    "Review the main lesson content before answering.",
                    "Xem lại nội dung chính của bài trước khi trả lời.",
                ),
                "explanation": question.get("explanation", ""),
                "explanation_translations": metadata.get("explanation_translations"),
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
            "title_translations": _native_text_translations(f"{TYPE_TITLES.get(lesson_type, 'Lesson')} recall"),
            "exercise_type": "text_input",
            "skill": lesson_type,
            "prompt": "Nhập lại từ khóa đầu tiên của bài.",
            "prompt_translations": _translations(
                "Type the first key word from the lesson.",
                "Nhập lại từ khóa đầu tiên của bài.",
            ),
            "correct_answer": answer,
            "expected_answer": answer,
            "hint": str(first_word.get("pinyin", "")),
            "hint_translations": _translations(str(first_word.get("pinyin", "")), str(first_word.get("pinyin", ""))),
            "explanation": f"Từ khóa đầu tiên là {answer}.",
            "explanation_translations": _translations(
                f"The first key word is {answer}.",
                f"Từ khóa đầu tiên là {answer}.",
            ),
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
        content["overview_translations"] = _native_text_translations(overview)

    objectives = content.get("learning_objectives")
    if isinstance(objectives, list) and "learning_objective_translations" not in content:
        content["learning_objective_translations"] = {
            "en": [_translate_native_text_en(objective) for objective in objectives],
            "vi": [_translate_native_text(objective) for objective in objectives],
        }

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
            point.setdefault("title_translations", _native_text_translations(title))
        if explanation:
            point.setdefault("explanation_translations", _native_text_translations(explanation))
        if point.get("common_mistakes") and "common_mistakes_translations" not in point:
            point["common_mistakes_translations"] = {
                "en": [_translate_native_text_en(item) for item in point["common_mistakes"]],
                "vi": [_translate_native_text(item) for item in point["common_mistakes"]],
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
            reading.setdefault("title_translations", _native_text_translations(reading.get("title")))
        if reading.get("english") or reading.get("vietnamese"):
            reading.setdefault("translations", _translations(reading.get("english"), reading.get("vietnamese")))
        for question in reading.get("questions") or []:
            if not isinstance(question, dict):
                continue
            if question.get("question"):
                question.setdefault("question_translations", _native_text_translations(question.get("question")))
            if question.get("answer"):
                question.setdefault("answer_translations", _native_text_translations(question.get("answer")))
            if question.get("explanation"):
                question.setdefault(
                    "explanation_translations",
                    _native_text_translations(question.get("explanation")),
                )

    listening = content.get("listening")
    if isinstance(listening, dict):
        if listening.get("english") or listening.get("vietnamese"):
            listening.setdefault("translations", _translations(listening.get("english"), listening.get("vietnamese")))
        if listening.get("task"):
            listening.setdefault("task_translations", _native_text_translations(listening.get("task")))
        if listening.get("answer"):
            listening.setdefault("answer_translations", _native_text_translations(listening.get("answer")))

    dialogue = content.get("dialogue")
    if isinstance(dialogue, dict):
        if dialogue.get("title"):
            dialogue.setdefault("title_translations", _native_text_translations(dialogue.get("title")))
        for line in dialogue.get("lines") or []:
            if isinstance(line, dict) and (line.get("english") or line.get("vietnamese")):
                line.setdefault("translations", _translations(line.get("english"), line.get("vietnamese")))
        if dialogue.get("cultural_note"):
            dialogue.setdefault(
                "cultural_note_translations",
                _native_text_translations(dialogue.get("cultural_note")),
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
                    exercise[translations_key] = _native_text_translations(value)
            options = exercise.get("options") or []
            if options and "options_translations" not in exercise:
                exercise["options_translations"] = _option_translations(options)

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
        levels[level_number].display_order = level_number
        levels[level_number].status = ContentStatus.PUBLISHED
    db.flush()
    return levels


def _ensure_courses(
    db: Session,
    levels: dict[int, HskLevel],
    content_lessons: list[dict[str, Any]],
) -> dict[tuple[int, str], Course]:
    courses = {
        (course.hsk_level.level_number, course.course_type): course
        for course in db.scalars(select(Course)).all()
    }
    course_types_by_level = {
        (int(item["hsk_level"]), item["lesson_type"]) for item in content_lessons
    }
    for level_number, course_type in sorted(
        course_types_by_level,
        key=lambda key: (key[0], COURSE_TYPE_ORDER.get(key[1], 99), key[1]),
    ):
        key = (level_number, course_type)
        course = courses.get(key)
        title = TYPE_TITLES.get(course_type, course_type.replace("_", " ").title())
        title_vi = TYPE_TITLES_VI.get(course_type, title)
        if course is None:
            course = Course(
                hsk_level_id=levels[level_number].id,
                course_type=course_type,
                sort_order=COURSE_TYPE_ORDER.get(course_type, 99),
            )
            db.add(course)
            courses[key] = course
        course.title = f"HSK {level_number} {title}"
        course.title_translations = {
            "en": course.title,
            "vi": f"HSK {level_number} - {title_vi}",
        }
        course.description = (
            f"Structured {title.lower()} lessons for HSK {level_number}."
        )
        course.description_translations = {
            "en": course.description,
            "vi": f"Các bài học {title_vi.lower()} có cấu trúc cho HSK {level_number}.",
        }
        course.sort_order = COURSE_TYPE_ORDER.get(course_type, 99)
        course.status = ContentStatus.PUBLISHED
        course.metadata_json = {"source": "seed_content"}
    db.flush()
    return courses


def _upsert_content_lessons(
    db: Session,
    levels: dict[int, HskLevel],
    courses: dict[tuple[int, str], Course],
    content_lessons: list[dict[str, Any]],
) -> None:
    existing_by_source_id = {
        lesson.content.get("source_id"): lesson
        for lesson in db.scalars(select(Lesson)).all()
        if isinstance(lesson.content, dict) and lesson.content.get("source_id")
    }

    for item in content_lessons:
        source_id = item["id"]
        hsk_level = int(item["hsk_level"])
        lesson = existing_by_source_id.get(source_id)
        if lesson is None:
            lesson = Lesson(hsk_level_id=levels[hsk_level].id)
            db.add(lesson)
            existing_by_source_id[source_id] = lesson

        title_translations = item.get("title_translations") or _lesson_title_translations(
            item["title"],
            item["lesson_type"],
        )
        description_translations = item.get("description_translations") or _lesson_description_translations(
            item.get("description"),
            item["lesson_type"],
            hsk_level,
            title_translations,
        )
        content = dict(item["content"])
        content["title_translations"] = title_translations
        if description_translations:
            content["description_translations"] = description_translations
        content = _augment_content_translations(content)
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
        content["question_translations"] = [
            _question_translation_payload(question)
            for question in item.get("questions", [])
        ]
        lesson.hsk_level_id = levels[hsk_level].id
        lesson.course_id = courses[(hsk_level, item["lesson_type"])].id
        lesson.title = item["title"]
        lesson.description = item.get("description")
        lesson.lesson_type = item["lesson_type"]
        lesson.sort_order = int(item["sort_order"])
        lesson.duration_minutes = int(item["duration_minutes"])
        lesson.content = content
        db.flush()

        existing_questions = {
            question.sort_order: question
            for question in db.scalars(
                select(Question).where(Question.lesson_id == lesson.id)
            ).all()
            if (question.metadata_json or {}).get("source")
            != "legacy_jsonb_practice"
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
            question.metadata_json = {
                **(question.metadata_json or {}),
                "source": "lesson_seed",
            }
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
        title = str(item["title"])
        mock_test = existing.get(title)
        if mock_test is None:
            mock_test = MockTest(title=title)
            db.add(mock_test)
        mock_test.hsk_level = int(str(item["hsk_level"]))
        mock_test.duration_minutes = int(str(item["duration_minutes"]))
        mock_test.question_count = int(str(item["question_count"]))



def seed_data(db: Session) -> None:
    from app.content_import import backfill_normalized_content
    from app.practice_engine import backfill_exercise_engine

    levels = _ensure_levels(db)
    content_lessons = _content_lessons()
    courses = _ensure_courses(db, levels, content_lessons)
    _upsert_content_lessons(db, levels, courses, content_lessons)
    backfill_normalized_content(db)
    backfill_exercise_engine(db)
    _upsert_achievements(db)
    _upsert_mock_tests(db)
    db.commit()
