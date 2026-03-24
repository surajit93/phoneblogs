import datetime
import json
import os
import random
import webbrowser

from seo_growth_utils import keyword_intent, score_keyword_opportunity

TRACKER_FILE = "data/backlinks/tracker.json"
DIST_FILE = "data/distribution/reddit_quora_posts.json"
OUTREACH_DIR = "site/outreach_posts"
TARGETS_FILE = "data/backlinks/targets.json"

TODAY = datetime.date.today().isoformat()
HIGH_INTENT = {"comparison", "commercial", "budget", "review"}


def load_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def load_backlink_targets():
    return load_json(TARGETS_FILE, [])


def score_target(target):
    keyword = target.get("keyword", "")
    intent = keyword_intent(keyword)
    authority_score = float(target.get("authority_weight", 0))
    cluster_score = float(target.get("cluster_priority", 0))
    ctr_score = float(target.get("ctr_score", 0))
    return (
        score_keyword_opportunity(keyword, [])
        + target.get("weight", 1) * 8
        + (18 if target.get("is_pillar") else 0)
        + (14 if intent in HIGH_INTENT else 0)
        + authority_score
        + cluster_score
        + ctr_score
        + len(target.get("supporting_reviews", [])) * 2
    )


def print_daily_targets():
    targets = load_backlink_targets()
    if not targets:
        print("[TARGETS] No backlink targets")
        return
    selected = sorted(targets, key=score_target, reverse=True)[:8]
    print("\n=== BACKLINK TARGETS ===\n")
    for t in selected:
        print(f"\n🔹 {t['keyword']}")
        print(f"Page: {t['target_page']}")
        print(f"Anchor: {t['anchor']}")
        print(f"Intent: {t.get('intent', 'n/a')} | Authority: {t.get('authority_weight', 0)} | CTR: {t.get('ctr_score', 0)}")
        reviews = t.get("supporting_reviews") or []
        if reviews:
            print(f"Support reviews: {', '.join(reviews[:3])}")
        if t.get("opportunities"):
            print(f"Search: {t['opportunities'][0]}")
        print("-" * 60)


def prioritize_distribution(posts):
    tracker = load_json(TRACKER_FILE, {})
    linked = {
        (entry.get("target") or entry.get("url") or "")
        for entry in tracker.get("links_acquired", [])
        if isinstance(entry, dict) and (entry.get("target") or entry.get("url"))
    }

    def sort_key(post):
        keyword = post.get("keyword", "")
        intent = keyword_intent(keyword)
        return (
            1 if post.get("target_url", "") not in linked else 0,
            1 if intent in HIGH_INTENT else 0,
            score_keyword_opportunity(keyword, []),
            1 if any(token in keyword.lower() for token in ("vs", "under", "best")) else 0,
        )

    return sorted(posts, key=sort_key, reverse=True)


def open_platforms():
    urls = [
        "https://www.reddit.com/r/smartphones/",
        "https://www.reddit.com/r/Android/",
        "https://www.quora.com/",
    ]
    for u in urls:
        webbrowser.open(u)


def run_distribution():
    posts = prioritize_distribution(load_json(DIST_FILE, []))
    tracker = load_json(TRACKER_FILE, {})
    used_keywords = {
        entry.get("keyword")
        for entry in tracker.get("posts", [])
        if isinstance(entry, dict) and entry.get("keyword")
    }
    fresh_posts = [
        p for p in posts
        if p.get("keyword") and p.get("keyword") not in used_keywords and keyword_intent(p.get("keyword", "")) in HIGH_INTENT
    ]
    if not fresh_posts:
        print("[DIST] No fresh posts available")
        return
    selected = fresh_posts[: min(5, len(fresh_posts))]
    print("\n=== COPY & POST ===\n")
    for p in selected:
        keyword = p.get("keyword", "")
        options = p.get("posts") or []
        if not options:
            continue
        msg = random.choice(options)
        url = p.get("target_url", "")
        print(f"\n🔹 {keyword}")
        print(f"{msg}\n\n👉 {url}")
        print("-" * 60)
        tracker.setdefault("posts", []).append({
            "keyword": keyword,
            "url": url,
            "target": url,
            "priority": score_keyword_opportunity(keyword, []),
            "date": TODAY,
        })
    save_json(TRACKER_FILE, tracker)


def run_outreach():
    if not os.path.isdir(OUTREACH_DIR):
        print("[OUTREACH] No outreach directory")
        return
    files = sorted(os.listdir(OUTREACH_DIR))
    tracker = load_json(TRACKER_FILE, {})
    sent_today = [x for x in tracker.get("outreach_sent", []) if isinstance(x, dict) and x.get("date") == TODAY]
    if len(sent_today) >= 5:
        print("[OUTREACH] Daily limit reached")
        return
    sent_files = {x.get("file") for x in tracker.get("outreach_sent", []) if isinstance(x, dict) and x.get("file")}
    remaining = [f for f in files if f not in sent_files]
    if not remaining:
        print("[OUTREACH] No new outreach files")
        return
    to_send = remaining[: min(5 - len(sent_today), len(remaining))]
    print("\n=== OUTREACH ===\n")
    for filename in to_send:
        path = os.path.join(OUTREACH_DIR, filename)
        with open(path, "r", encoding="utf-8") as file:
            content = file.read()
        print(f"\n📧 {filename}\n")
        print(content[:500])
        print("-" * 60)
        tracker.setdefault("outreach_sent", []).append({"file": filename, "date": TODAY})
    save_json(TRACKER_FILE, tracker)


def summary():
    tracker = load_json(TRACKER_FILE, {})
    print("\n=== STATS ===")
    print(f"Total Outreach: {len(tracker.get('outreach_sent', []))}")
    print(f"Links Acquired: {len(tracker.get('links_acquired', []))}")
    print(f"Posts Scheduled: {len(tracker.get('posts', []))}")


def weekly_summary():
    tracker = load_json(TRACKER_FILE, {})
    last_7 = []
    for x in tracker.get("outreach_sent", []):
        if not isinstance(x, dict) or not x.get("date"):
            continue
        try:
            if (datetime.date.today() - datetime.date.fromisoformat(x["date"])).days <= 7:
                last_7.append(x)
        except ValueError:
            continue
    print("\n=== WEEKLY PROGRESS ===")
    print(f"Outreach (7d): {len(last_7)}")
    print(f"Total Links: {len(tracker.get('links_acquired', []))}")


def run():
    print("\n🔥 GROWTH ENGINE STARTED 🔥\n")
    open_platforms()
    run_distribution()
    print_daily_targets()
    run_outreach()
    summary()
    weekly_summary()
    print("\n✅ DONE\n")


if __name__ == "__main__":
    run()
