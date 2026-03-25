# >>> UPDATED START
#!/usr/bin/env python3

import datetime
import os

from seo_growth_utils import deterministic_choice, load_json, save_json

TRACKER_FILE = "data/backlinks/tracker.json"
TARGETS_FILE = "data/backlinks/targets.json"
OUTREACH_OUTPUT = "data/distribution/outreach_messages.json"
COMMUNITY_OUTPUT = "data/distribution/reddit_quora_posts.json"

TODAY = datetime.date.today().isoformat()


def load_tracker():
    tracker = load_json(
        TRACKER_FILE,
        {
            "generated_at": TODAY,
            "outreach": [],
            "community_posts": [],
            "pipeline": {"sent": 0, "replied": 0, "converted": 0},
        },
    )
    tracker.setdefault("outreach", [])
    tracker.setdefault("community_posts", [])
    tracker.setdefault("pipeline", {"sent": 0, "replied": 0, "converted": 0})
    return tracker


def outreach_templates():
    return [
        "Subject: Data-backed resource for your audience on {keyword}\n\nHi {name},\nI noticed your readers ask about {keyword}. We published a decision-first guide with contradictory viewpoints, failure cases, and buyer segmentation: {url}.\nIf useful, feel free to cite it in your resource section.\n\nThanks,\n{sender}",
        "Subject: Could this strengthen your {keyword} article?\n\nHey {name},\nYour post on {keyword} is strong. We ran a fresh framework including hidden trade-offs and who should NOT buy: {url}.\nWould you consider adding it as an external reference for practical decision support?\n\nBest,\n{sender}",
        "Subject: New benchmark-style explainer for {keyword}\n\nHi {name},\nWe compiled real-world usage evidence and failure scenarios around {keyword}: {url}.\nIt may complement your current recommendations and reduce generic advice for readers.\n\nRegards,\n{sender}",
    ]


def reddit_templates():
    return [
        "I tested this deeply because I kept seeing confusion around **{keyword}**. This guide breaks down contradictory opinions, failure cases, and who should avoid certain phones: {url}",
        "If you're choosing right now, this {keyword} analysis helped me avoid a bad buy. It compares trade-offs in real-world usage instead of specs only: {url}",
        "Posting this for anyone debating {keyword}: it includes hidden trade-offs + better alternatives + buyer framework. Might save you money/time: {url}",
    ]


def quora_templates():
    return [
        "Short answer: it depends on workload and failure tolerance. Long answer with decision framework + practical scenarios here: {url}",
        "Most answers ignore hidden trade-offs. This resource covers contradictory viewpoints and who should NOT buy: {url}",
        "I recommend evaluating this with real-world constraints (heat, network, battery wear). Detailed structure: {url}",
    ]


def prioritize_targets(targets, tracker):
    converted_urls = {x.get("target_page") for x in tracker.get("outreach", []) if x.get("status") == "converted"}
    ranked = sorted(
        targets,
        key=lambda t: (
            t.get("target_page") in converted_urls,
            -float(t.get("roi_score", 0)),
        ),
    )
    return ranked


def generate_outreach_messages(targets, daily_limit=25):
    messages = []
    templates = outreach_templates()
    prospects = ["Editor", "Site Owner", "Community Manager", "Contributor"]

    for i, target in enumerate(targets[:daily_limit]):
        template = templates[i % len(templates)]
        message = template.format(
            keyword=target["keyword"],
            url=target["target_page"],
            name=prospects[i % len(prospects)],
            sender="PhoneRank Growth Team",
        )
        messages.append(
            {
                "id": f"outreach-{TODAY}-{i+1:03d}",
                "date": TODAY,
                "target_page": target["target_page"],
                "keyword": target["keyword"],
                "anchor_text": deterministic_choice(target.get("anchor_variants", [target.get("anchor", target["keyword"])]), f"anchor-{i}"),
                "channel": "email",
                "message": message,
                "status": "sent",
            }
        )
    return messages


def generate_community_posts(targets, daily_limit=30):
    posts = []
    reddit = reddit_templates()
    quora = quora_templates()

    for i, target in enumerate(targets[:daily_limit]):
        posts.append(
            {
                "id": f"reddit-{TODAY}-{i+1:03d}",
                "date": TODAY,
                "platform": "reddit",
                "subreddit": "r/smartphones",
                "keyword": target["keyword"],
                "target_url": target["target_page"],
                "anchor_text": target.get("anchor", target["keyword"]),
                "post": reddit[i % len(reddit)].format(keyword=target["keyword"], url=target["target_page"]),
                "status": "sent",
            }
        )
        posts.append(
            {
                "id": f"quora-{TODAY}-{i+1:03d}",
                "date": TODAY,
                "platform": "quora",
                "topic": "Smartphones",
                "keyword": target["keyword"],
                "target_url": target["target_page"],
                "anchor_text": target.get("anchor", target["keyword"]),
                "post": quora[i % len(quora)].format(url=target["target_page"]),
                "status": "sent",
            }
        )
    return posts


def merge_tracker(tracker, outreach, community_posts):
    tracker["outreach"].extend(outreach)
    tracker["community_posts"].extend(community_posts)

    sent = len([x for x in tracker["outreach"] if x.get("status") == "sent"]) + len(
        [x for x in tracker["community_posts"] if x.get("status") == "sent"]
    )
    replied = len([x for x in tracker["outreach"] if x.get("status") == "replied"]) + len(
        [x for x in tracker["community_posts"] if x.get("status") == "replied"]
    )
    converted = len([x for x in tracker["outreach"] if x.get("status") == "converted"]) + len(
        [x for x in tracker["community_posts"] if x.get("status") == "converted"]
    )

    tracker["pipeline"] = {"sent": sent, "replied": replied, "converted": converted}
    tracker["generated_at"] = TODAY
    return tracker


def run():
    os.makedirs("data/distribution", exist_ok=True)
    os.makedirs("data/backlinks", exist_ok=True)

    tracker = load_tracker()
    targets = load_json(TARGETS_FILE, [])
    if not targets:
        print("[GROWTH] no backlink targets found")
        return

    ranked_targets = prioritize_targets(targets, tracker)
    outreach = generate_outreach_messages(ranked_targets, daily_limit=30)
    community_posts = generate_community_posts(ranked_targets, daily_limit=20)

    save_json(OUTREACH_OUTPUT, outreach)
    save_json(COMMUNITY_OUTPUT, community_posts)

    tracker = merge_tracker(tracker, outreach, community_posts)
    save_json(TRACKER_FILE, tracker)

    print(
        f"[GROWTH] outreach_sent={len(outreach)} community_posts={len(community_posts)} "
        f"pipeline={tracker['pipeline']}"
    )


if __name__ == "__main__":
    run()
# >>> UPDATED END
