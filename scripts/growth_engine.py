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
def load_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return default

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
    tracker = load_json(TRACKER_FILE, {})

    used_keywords = set(tracker.get("posted_keywords", []))

    fresh_posts = [p for p in posts if p["keyword"] not in used_keywords]

    if not fresh_posts:
        print("[DIST] No fresh posts available")
        return

    selected = random.sample(fresh_posts, min(3, len(fresh_posts)))

    print("\n=== COPY & POST ===\n")

    for p in selected:
        print(f"\n🔹 {p['keyword']}")
        print(f"{random.choice(p['posts'])}")
        print("-" * 60)

        tracker.setdefault("posted_keywords", []).append(p["keyword"])

    save_json(TRACKER_FILE, tracker)

# -------------------------
# OUTREACH (DAILY LIMIT + NO DUPLICATE)
# -------------------------
def run_outreach():
    files = os.listdir(OUTREACH_DIR)
    tracker = load_json(TRACKER_FILE, {})

    sent_today = [
        x for x in tracker.get("outreach_sent", [])
        if x["date"] == TODAY
    ]

    if len(sent_today) >= 5:
        print("[OUTREACH] Daily limit reached")
        return

    sent_files = set(x["file"] for x in tracker.get("outreach_sent", []))

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
# MAIN
# -------------------------
def run():
    print("\n🔥 GROWTH ENGINE STARTED 🔥\n")

    open_platforms()
    run_distribution()
    run_outreach()
    summary()

    print("\n✅ DONE\n")

if __name__ == "__main__":
    run()
