"""產生【假資料 FAKE / SYNTHETIC】。不是任何真實直播的聊天。"""
import json, random
random.seed(42)
users = [f"fake_user_{i:02d}" for i in range(40)]
filler = ["今天吃什麼", "安安", "這關好難", "?", "加油", "音樂好聽"]
def chat(dur=7200):
    m = [{"t": random.uniform(0, dur), "user": random.choice(users), "text": random.choice(filler)} for _ in range(dur // 30)]
    m += [{"t": random.uniform(0, 240), "user": random.choice(users), "text": "安安"} for _ in range(60)]  # 開場打招呼假峰值
    for c, words in [(2400, ["笑死", "LUL", "笑死笑死"]), (4500, ["7777", "777", "幹 好強"])]:  # 真峰值（多人）
        m += [{"t": c + random.uniform(0, 40), "user": random.choice(users), "text": random.choice(words)} for _ in range(45)]
    m += [{"t": 6000 + random.uniform(0, 50), "user": "fake_spammer", "text": "洗版洗版"} for _ in range(50)]  # 單人洗版
    return m
json.dump(chat(), open("tests/FAKE_chat_active.json", "w"), ensure_ascii=False)
json.dump([{"t": i * 200.0, "user": random.choice(["fake_a", "fake_b"]), "text": "hi"} for i in range(30)] +
          [{"t": 3000 + i, "user": "fake_spammer", "text": "洗版"} for i in range(8)], open("tests/FAKE_chat_quiet.json", "w"), ensure_ascii=False)
