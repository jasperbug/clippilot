"""以假資料測試（FAKE / SYNTHETIC）。python -m pytest -q tests 或 python tests/test_all.py"""
import json, os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from peaks import analyze, load
from filters import ProcessedStore, should_process
D = os.path.dirname(os.path.abspath(__file__))

def test_active():
    r = analyze(load(f"{D}/FAKE_chat_active.json"), "twitch", "https://www.twitch.tv/videos/FAKE", top=5, duration=7200)
    times = [c["peak_time"] for c in r["candidates"]]
    assert r["status"] == "ok" and {t[:5] for t in times[:2]} <= {"00:39", "00:40", "01:14", "01:15"}, times
    assert any(w["user"] == "fake_spammer" for w in r["spam_warnings"])
    assert not any(c["peak_time"].startswith("01:40") and "single_viewer_dominated" not in c["flags"] for c in r["candidates"])
    return r

def test_quiet():
    r = analyze(load(f"{D}/FAKE_chat_quiet.json"), "youtube", duration=6000)
    assert r["status"] == "聊天反應不足" and r["spam_warnings"]; return r

def test_filters():
    with tempfile.TemporaryDirectory() as d:
        s = ProcessedStore(f"{d}/processed.json")
        assert should_process("twitch", {"id": "1", "type": "highlight"}, s)[1] == "not_live_archive"
        assert should_process("twitch", {"id": "1", "type": "archive"}, s)[0]
        s.add("twitch:1"); s = ProcessedStore(f"{d}/processed.json")
        assert should_process("twitch", {"id": "1", "type": "archive"}, s)[1] == "duplicate"
        assert should_process("youtube", {"id": "s", "live_status": "not_live"}, s)[1] == "not_live_archive"
        assert should_process("youtube", {"id": "y", "liveStreamingDetails": {"actualEndTime": "x"}}, s)[0]
        assert should_process("youtube", {"id": "z", "live_status": "was_live", "description": "#streamer-copilot-clip"}, s)[1] == "bot_generated"

def test_spam_threshold():
    from peaks import spam_warnings
    seven = [{"t": i * 5.0, "user": "fake_x", "text": "spam"} for i in range(7)]
    eight = [{"t": i * 5.0, "user": "fake_x", "text": "spam"} for i in range(8)]
    assert spam_warnings(seven) == [] and spam_warnings(eight)

test_spam_threshold(); print("spam threshold test PASS (FAKE DATA)")

if __name__ == "__main__":
    _ts = [f for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for f in _ts: f(); print("ok", f.__name__)
    print(f"{len(_ts)} tests PASS (FAKE/MOCKED DATA)")
