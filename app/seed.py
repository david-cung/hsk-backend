from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Achievement, HskLevel, Lesson, MockTest, Question


LESSONS = [
    {
        "level_number": 1,
        "title": "Greetings and Names",
        "description": "Basic greetings, names, and polite introductions.",
        "lesson_type": "vocabulary",
        "sort_order": 1,
        "duration_minutes": 12,
        "content": {
            "vocabulary": [
                {"hanzi": "你好", "pinyin": "ni hao", "meaning": "hello"},
                {"hanzi": "谢谢", "pinyin": "xie xie", "meaning": "thank you"},
                {"hanzi": "名字", "pinyin": "ming zi", "meaning": "name"},
            ],
            "tip": "Use ni hao for most everyday greetings.",
        },
        "questions": [
            {
                "prompt": "What does ni hao mean?",
                "options": ["Hello", "Goodbye", "Teacher", "Water"],
                "correct_answer": "Hello",
                "explanation": "Ni hao is the standard greeting for hello.",
            },
            {
                "prompt": "Choose the meaning of xie xie.",
                "options": ["Thank you", "Sorry", "Please", "Name"],
                "correct_answer": "Thank you",
                "explanation": "Xie xie means thank you.",
            },
        ],
    },
    {
        "level_number": 1,
        "title": "Numbers and Dates",
        "description": "Count from 1 to 10 and ask simple date questions.",
        "lesson_type": "listening",
        "sort_order": 2,
        "duration_minutes": 10,
        "content": {
            "transcript": [
                {"hanzi": "一二三", "pinyin": "yi er san", "meaning": "one two three"},
                {"hanzi": "今天几号", "pinyin": "jin tian ji hao", "meaning": "what date is today"},
            ]
        },
        "questions": [
            {
                "prompt": "Which option means three?",
                "options": ["一", "二", "三", "十"],
                "correct_answer": "三",
                "explanation": "San is written as 三.",
            }
        ],
    },
    {
        "level_number": 2,
        "title": "Daily Routines",
        "description": "Talk about common daily actions and time.",
        "lesson_type": "grammar",
        "sort_order": 1,
        "duration_minutes": 15,
        "content": {
            "grammar_points": [
                {
                    "title": "Time before verb",
                    "explanation": "In Mandarin, time words often appear before the verb phrase.",
                    "examples": [
                        {"hanzi": "我今天学习汉语", "pinyin": "wo jin tian xue xi han yu", "meaning": "I study Chinese today"}
                    ],
                }
            ]
        },
        "questions": [
            {
                "prompt": "Where does a time word usually go?",
                "options": ["Before the verb phrase", "After every noun", "Only at sentence end", "It is never used"],
                "correct_answer": "Before the verb phrase",
                "explanation": "Time words commonly come before the verb phrase.",
            }
        ],
    },
    {
        "level_number": 3,
        "title": "Short Reading: At the Cafe",
        "description": "Read a short conversation about ordering drinks.",
        "lesson_type": "reading",
        "sort_order": 1,
        "duration_minutes": 18,
        "content": {
            "passage_title": "At the Cafe",
            "passage": [
                {"hanzi": "我想喝一杯茶", "pinyin": "wo xiang he yi bei cha", "meaning": "I would like to drink a cup of tea"},
                {"hanzi": "这个咖啡很热", "pinyin": "zhe ge ka fei hen re", "meaning": "This coffee is hot"},
            ],
        },
        "questions": [
            {
                "prompt": "What does cha mean?",
                "options": ["Tea", "Coffee", "Rice", "Book"],
                "correct_answer": "Tea",
                "explanation": "Cha means tea.",
            }
        ],
    },
]


def seed_data(db: Session) -> None:
    if db.scalar(select(HskLevel.id).limit(1)):
        return

    levels = {}
    for level_number in range(1, 7):
        level = HskLevel(
            level_number=level_number,
            title=f"HSK {level_number}",
            description=f"Structured Mandarin lessons for HSK {level_number}.",
            total_characters=[150, 300, 600, 1200, 2500, 5000][level_number - 1],
        )
        db.add(level)
        levels[level_number] = level
    db.flush()

    for item in LESSONS:
        lesson = Lesson(
            hsk_level_id=levels[item["level_number"]].id,
            title=item["title"],
            description=item["description"],
            lesson_type=item["lesson_type"],
            sort_order=item["sort_order"],
            duration_minutes=item["duration_minutes"],
            content=item["content"],
        )
        db.add(lesson)
        db.flush()
        for index, q in enumerate(item["questions"], start=1):
            db.add(
                Question(
                    lesson_id=lesson.id,
                    question_type="multiple_choice",
                    prompt=q["prompt"],
                    options=q["options"],
                    correct_answer=q["correct_answer"],
                    explanation=q["explanation"],
                    sort_order=index,
                )
            )

    db.add_all(
        [
            Achievement(code="first_quiz", title="First Quiz", description="Submit your first quiz.", icon="school"),
            Achievement(code="first_word", title="Word Collector", description="Save your first word.", icon="bookmark"),
            Achievement(code="three_lessons", title="Momentum", description="Complete three lessons.", icon="flame"),
        ]
    )
    db.add_all(
        [
            MockTest(title="HSK 1 Mini Mock Test", hsk_level=1, duration_minutes=20, question_count=20),
            MockTest(title="HSK 2 Mini Mock Test", hsk_level=2, duration_minutes=25, question_count=25),
            MockTest(title="HSK 3 Mini Mock Test", hsk_level=3, duration_minutes=35, question_count=30),
        ]
    )
    db.commit()
