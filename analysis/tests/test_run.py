"""run.py 輪詢／守門／失敗計數測試：全部 mock，假資料（FAKE）。"""
import io, json, os, sys, tempfile, contextlib
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import fetch, run

FAKE_CHAT = [{"t": float(i * 10), "user": f"fake_u{i % 12}", "text": "笑死" if 600 < i * 10 < 660 else "hi"} for i in range(400)]
META = {  # 假影片
    "y1": {"live_status": "was_live", "description": ""},
    "y2": {"live_status": "not_live", "description": ""},                       # 一般上傳／Shorts
    "y3": {"live_status": "was_live", "description": "… #streamer-copilot-clip"},  # bot 自產
    "y4": {"live_status": "was_live", "description": ""},
    "t1": {"type": "archive", "was_live": True}, "t2": {"type": "other"},
}
def fake_meta(platform, vid):
    m = dict(META[vid], id=vid, url=f"https://fake.invalid/{vid}", title="FAKE", duration=4000)
    return m
def patch(listing, fail=False):
    fetch.video_meta = fake_meta
    fetch.twitch_chat = fetch.youtube_chat = lambda vid, wd: FAKE_CHAT
    def lst(*a, **k):
        if fail: raise RuntimeError("FAKE yt-dlp failure")
        return listing
    fetch.list_youtube_streams = fetch.list_twitch_archives = lst
def go(args):
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()): return run.main(args)

def test_all():
    with tempfile.TemporaryDirectory() as d:
        base = ["--state-dir", d]
        patch(["y1", "y2", "y3", "y4"])
        out = go(["--platform", "youtube", "--channel", "@fake", "--poll"] + base)
        assert isinstance(out, list) and [r["video"]["id"] for r in out] == ["y1", "y4"], out
        assert go(["--platform", "youtube", "--channel", "@fake", "--poll"] + base)["status"] == "no_new_video"  # 去重
        patch(["t2", "t1"])
        out = go(["--platform", "twitch", "--channel", "fake", "--initial-wait", "0", "--retries", "0"] + base)
        assert out["video"]["id"] == "t1"   # t2 非 archive 被跳過
        assert go(["--platform", "twitch", "--channel", "fake", "--retries", "0"] + base)["status"] == "no_new_video"
        # dry-run 不寫 processed
        d2 = tempfile.mkdtemp(); patch(["y1"])
        go(["--platform", "youtube", "--channel", "@fake", "--poll", "--dry-run", "--state-dir", d2])
        assert not os.path.exists(os.path.join(d2, "processed.json"))
        # 失敗計數：1 次不報、2 次報、成功歸零
        patch([], fail=True)
        o1 = go(["--platform", "youtube", "--channel", "@fake", "--poll"] + base)
        o2 = go(["--platform", "youtube", "--channel", "@fake", "--poll"] + base)
        assert o1["report_failure"] is False and o2["report_failure"] is True and o2["consecutive_failures"] == 2
        patch([]); go(["--platform", "youtube", "--channel", "@fake", "--poll"] + base)
        assert json.load(open(os.path.join(d, "fetch_failures.json")))["youtube"]["count"] == 0
        patch([], fail=True)
        assert go(["--platform", "youtube", "--channel", "@fake", "--poll"] + base)["report_failure"] is False
        # 單支失敗：其他照常處理，不算連續失敗
        d3 = tempfile.mkdtemp(); patch(["y1", "bad"])
        orig = fetch.video_meta
        fetch.video_meta = lambda p, v: (_ for _ in ()).throw(RuntimeError("FAKE bot check")) if v == "bad" else orig(p, v)
        out = go(["--platform", "youtube", "--channel", "@fake", "--poll", "--state-dir", d3])
        assert out[0]["video"]["id"] == "y1" and out[-1]["status"] == "partial_errors"
        assert fetch.channel_url_youtube("@fake_channel").endswith("/@fake_channel/streams")
        # 單支失敗：其他照常處理，不算連續失敗
        d3 = tempfile.mkdtemp(); patch(["y1", "bad"])
        orig = fetch.video_meta
        fetch.video_meta = lambda p, v: (_ for _ in ()).throw(RuntimeError("FAKE bot check")) if v == "bad" else orig(p, v)
        out = go(["--platform", "youtube", "--channel", "@fake", "--poll", "--state-dir", d3])
        assert out[0]["video"]["id"] == "y1" and out[-1]["status"] == "partial_errors"
        assert fetch.channel_url_youtube("https://www.youtube.com/@x/videos") == "https://www.youtube.com/@x/streams"

def test_init_and_urls():
    from run import normalize_id
    assert normalize_id("twitch", "https://www.twitch.tv/videos/123456789") == "123456789"
    assert normalize_id("twitch", "v123") == "123"
    for u in ["https://www.youtube.com/watch?v=AbCdEfGhIjK&t=10s", "https://youtu.be/AbCdEfGhIjK", "https://www.youtube.com/live/AbCdEfGhIjK", "AbCdEfGhIjK"]:
        assert normalize_id("youtube", u) == "AbCdEfGhIjK", u
    with tempfile.TemporaryDirectory() as d:
        patch(["y1", "y2", "y3", "y4"])
        calls = []; orig = fetch.youtube_chat
        fetch.youtube_chat = lambda v, w: calls.append(v) or FAKE_CHAT
        dr = go(["--platform", "youtube", "--channel", "@fake", "--init", "--dry-run", "--state-dir", d])
        assert dr["marked_count"] == 2 and not os.path.exists(os.path.join(d, "processed.json"))
        out = go(["--platform", "youtube", "--channel", "@fake", "--init", "--state-dir", d])
        assert out["marked_count"] == 2 and out["marked"] == ["y1", "y4"] and calls == []  # 沒分析
        assert {x["reason"] for x in out["skipped"]} == {"not_live_archive", "bot_generated"}
        assert go(["--platform", "youtube", "--channel", "@fake", "--poll", "--state-dir", d])["status"] == "no_new_video"
        # --id 接受網址，可試跑舊場次（y1 已 init → duplicate；--force 才能重跑）
        META["AbCdEfGhIjK"] = {"live_status": "was_live", "description": ""}
        r = go(["--platform", "youtube", "--id", "https://youtu.be/AbCdEfGhIjK", "--dry-run", "--state-dir", d])
        assert r["status"] == "ok" and r["video"]["id"] == "AbCdEfGhIjK"
        go(["--platform", "youtube", "--id", "AbCdEfGhIjK", "--state-dir", d])
        assert go(["--platform", "youtube", "--id", "https://www.youtube.com/watch?v=AbCdEfGhIjK", "--state-dir", d])["reason"] == "duplicate"
        bad = go(["--platform", "youtube", "--id", "https://example.com/x", "--state-dir", d])
        assert bad["status"] == "invalid_id"

def test_poll_gate_live_and_fresh():
    import argparse, filters
    from filters import poll_gate
    now = 1_800_000_000
    assert poll_gate({"live_status": "is_live"}, now) == (False, "live_now")
    assert poll_gate({"is_live": True}, now) == (False, "live_now")
    assert poll_gate({"live_status": "post_live"}, now)[1] == "live_now"
    assert poll_gate({"timestamp": now - 3600, "duration": 3600 - 300}, now) == (False, "too_fresh")  # 5 分鐘前結束
    assert poll_gate({"timestamp": now - 3600, "duration": 3600 - 900}, now) == (True, "ok")
    assert poll_gate({"release_timestamp": now - 7200, "timestamp": now - 60, "duration": 3600}, now) == (True, "ok")
    assert poll_gate({"live_status": "was_live"}, now) == (True, "ok")  # 無時間資訊則放行

    # run.process：--poll 下直播中／太新都 skipped 且不寫 processed
    with tempfile.TemporaryDirectory() as d:
        store = run.ProcessedStore(os.path.join(d, "processed.json"))
        a = argparse.Namespace(platform="youtube", force=False, poll=True, dry_run=False, state_dir=d, top=8)
        orig = fetch.video_meta
        try:
            import time as _t
            for meta, why in [({"live_status": "is_live"}, "live_now"),
                              ({"live_status": "was_live", "timestamp": _t.time() - 1000, "duration": 900}, "too_fresh")]:
                fetch.video_meta = lambda p, v, m=meta: {"id": v, "url": "u", "description": "", **m}
                res, done = run.process(a, "FAKEvid0001", store, [], [])
                assert (done, res["reason"]) == (False, why)
                assert not store.seen("youtube:FAKEvid0001")
                assert not os.path.exists(os.path.join(d, "processed.json"))
            # 非 --poll（手動 --id）不受太新限制
            a.poll = False; a.check_only = True
            fetch.video_meta = lambda p, v: {"id": v, "url": "u", "description": "", "live_status": "was_live", "timestamp": _t.time() - 100, "duration": 50}
            assert run.process(a, "FAKEvid0001", store, [], [])[1] is True
        finally:
            fetch.video_meta = orig

def test_youtube_failures_log():
    import argparse
    orig = fetch.video_meta
    def boom(p, v): raise RuntimeError("Sign in to confirm you're not a bot\nFAKE")
    try:
        fetch.video_meta = boom
        orig_list = run.list_candidates
        run.list_candidates = lambda a: ["FAKEvid0001", "FAKEvid0002"]
        for dry in (False, True):
            with tempfile.TemporaryDirectory() as d:
                a = argparse.Namespace(platform="youtube", channel="x", id=None, init=False, poll=True, force=False, dry_run=dry,
                    check_only=dry, state_dir=d, top=8, own_uploads=None, reaction_words="", initial_wait=0, retries=0, retry_wait=0)
                try: run.run(a); assert False, "should raise"
                except RuntimeError: pass
                log = os.path.join(d, "youtube_failures.log")
                assert not os.path.exists(os.path.join(d, "processed.json"))
                if dry: assert not os.path.exists(log)
                else:
                    lines = open(log, encoding="utf-8").read().splitlines()
                    assert [l.split("\t")[1] for l in lines] == ["FAKEvid0001", "FAKEvid0002"]
                    assert "not a bot" in lines[0] and "\n" not in lines[0]
        # twitch 失敗不寫 youtube log
        with tempfile.TemporaryDirectory() as d:
            a = argparse.Namespace(platform="twitch", channel="x", id=None, init=False, poll=True, force=False, dry_run=False,
                check_only=False, state_dir=d, top=8, own_uploads=None, reaction_words="", initial_wait=0, retries=0, retry_wait=0)
            try: run.run(a)
            except RuntimeError: pass
            assert not os.path.exists(os.path.join(d, "youtube_failures.log"))
    finally:
        fetch.video_meta = orig; run.list_candidates = orig_list

if __name__ == "__main__":
    _ts = [f for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for f in _ts: f(); print("ok", f.__name__)
    print(f"{len(_ts)} tests PASS (FAKE/MOCKED DATA)")
