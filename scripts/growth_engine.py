import json
import random
import datetime
import os
import webbrowser

TRACKER_FILE = "data/backlinks/tracker.json"
DIST_FILE = "data/distribution/reddit_quora_posts.json"
OUTREACH_DIR = "site/outreach_posts"

TODAY = datetime.date.today().isoformat()

# -------------------------
# SAFE LOAD / SAVE
# -------------------------

# -------------------------
# LOAD BACKLINK TARGETS
# -------------------------
def load_backlink_targets():
    return load_json("data/backlinks/targets.json", [])

# -------------------------
# PRINT DAILY TARGETS
# -------------------------
def print_daily_targets():
    targets = load_backlink_targets()

    if not targets:
        print("[TARGETS] No backlink targets")
        return

    selected = random.sample(targets, min(5, len(targets)))

    print("\n=== BACKLINK TARGETS ===\n")

    for t in selected:
        print(f"\n🔹 {t['keyword']}")
        print(f"Page: {t['target_page']}")
        print(f"Anchor: {t['anchor']}")
        print(f"Search: {t['opportunities'][0]}")
        print("-" * 60)


def load_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return default

# -------------------------
# PRIORITIZE DISTRIBUTION
# -------------------------
def prioritize_distribution(posts):
    tracker = load_json(TRACKER_FILE, {})
    links_acquired = tracker.get("links_acquired", []) or []
    linked = {
        (entry.get("target") or entry.get("url") or "")
        for entry in links_acquired
        if isinstance(entry, dict) and (entry.get("target") or entry.get("url"))
    }

    posts.sort(
        key=lambda x: x.get("target_url", "") in linked,
        reverse=True
    )

    return posts

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

# -------------------------
# OPEN PLATFORMS
# -------------------------
def open_platforms():
    urls = [
        "https://www.reddit.com/r/smartphones/",
        "https://www.reddit.com/r/Android/",
        "https://www.quora.com/"
    ]
    for u in urls:
        webbrowser.open(u)

# -------------------------
# DISTRIBUTION (NO REPEAT)
# -------------------------
def run_distribution():
    posts = load_json(DIST_FILE, [])
    posts = prioritize_distribution(posts)
    tracker = load_json(TRACKER_FILE, {})

    used_keywords = {
        entry.get("keyword")
        for entry in tracker.get("posts", [])
        if entry.get("keyword")
    }

    fresh_posts = [p for p in posts if p.get("keyword") and p.get("keyword") not in used_keywords]

    if not fresh_posts:
        print("[DIST] No fresh posts available")
        return

    selected = random.sample(fresh_posts, min(3, len(fresh_posts)))

    print("\n=== COPY & POST ===\n")

    for p in selected:
        keyword = p.get("keyword", "")
        post_options = p.get("posts") or []
        if not post_options:
            continue

        print(f"\n🔹 {keyword}")
        msg = random.choice(post_options)
        url = p.get("target_url", "")
        print(f"{msg}\n\n👉 {url}")
        print("-" * 60)

        tracker.setdefault("posts", []).append({
            "keyword": keyword,
            "url": url,
            "target": url,
            "date": TODAY
        })

    save_json(TRACKER_FILE, tracker)

# -------------------------
# OUTREACH (DAILY LIMIT + NO DUPLICATE)
# -------------------------
def run_outreach():
    files = os.listdir(OUTREACH_DIR)
    tracker = load_json(TRACKER_FILE, {})

    sent_today = [
        x for x in tracker.get("outreach_sent", [])
        if isinstance(x, dict) and x.get("date") == TODAY
    ]

    if len(sent_today) >= 5:
        print("[OUTREACH] Daily limit reached")
        return

    sent_files = {x.get("file") for x in tracker.get("outreach_sent", []) if isinstance(x, dict) and x.get("file")}

    remaining = [f for f in files if f not in sent_files]

    if not remaining:
        print("[OUTREACH] No new outreach files")
        return

    to_send = random.sample(remaining, min(5 - len(sent_today), len(remaining)))

    print("\n=== OUTREACH ===\n")

    for f in to_send:
        path = os.path.join(OUTREACH_DIR, f)

        with open(path, "r", encoding="utf-8") as file:
            content = file.read()

        print(f"\n📧 {f}\n")
        print(content[:400])
        print("-" * 60)

        tracker.setdefault("outreach_sent", []).append({
            "file": f,
            "date": TODAY
        })

    save_json(TRACKER_FILE, tracker)

# -------------------------
# SUMMARY
# -------------------------
def summary():
    tracker = load_json(TRACKER_FILE, {})

    print("\n=== STATS ===")
    print(f"Total Outreach: {len(tracker.get('outreach_sent', []))}")
    print(f"Links Acquired: {len(tracker.get('links_acquired', []))}")

# -------------------------
# WEEKLY SUMMARY
# -------------------------
def weekly_summary():
    tracker = load_json(TRACKER_FILE, {})

    last_7 = []
    for x in tracker.get("outreach_sent", []):
        if not isinstance(x, dict):
            continue

        sent_date = x.get("date")
        if not sent_date:
            continue

        try:
            if (datetime.date.today() - datetime.date.fromisoformat(sent_date)).days <= 7:
                last_7.append(x)
        except ValueError:
            continue

    print("\n=== WEEKLY PROGRESS ===")
    print(f"Outreach (7d): {len(last_7)}")
    print(f"Total Links: {len(tracker.get('links_acquired', []))}")

# -------------------------
# MAIN
# -------------------------
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
