# scripts/bootstrap_repo.py

import os
from pathlib import Path

BASE = Path(".")

dirs = [
    "site/assets/css",
    "site/assets/js",
    "site/assets/images",

    "pages/phones",
    "pages/laptops",
    "pages/gpus",
    "pages/cameras",
    "pages/batteries",
    "pages/comparisons",
    "pages/price",
    "pages/features",
    "pages/launches",

    "data/phones",
    "data/laptops",
    "data/gpus",
    "data/cameras",
    "data/batteries",
    "data/benchmarks",

    "templates/layouts",
    "templates/components",
    "templates/pages",

    "scripts/scrape",
    "scripts/processors",
    "scripts/generators",

    "seo",
    "config",
    "logs"
]

files = {
    "site/index.html": "<h1>PhoneBlogs</h1>",
    "site/robots.txt": "User-agent: *\nAllow: /",
    "site/sitemap.xml": "",

    "data/phones/phones.json": "[]",
    "data/benchmarks/cpu_scores.json": "{}",
    "data/benchmarks/gpu_scores.json": "{}",
    "data/benchmarks/battery_tests.json": "{}",

    "templates/layouts/base.html": "<html><body>{{content}}</body></html>",
    "templates/layouts/device_page.html": "<h1>{{device}}</h1>",
    "templates/layouts/comparison_page.html": "<h1>{{a}} vs {{b}}</h1>",

    "templates/components/spec_table.html": "",
    "templates/components/comparison_table.html": "",
    "templates/components/ranking_table.html": "",

    "templates/pages/device.html": "",
    "templates/pages/comparison.html": "",
    "templates/pages/price_list.html": "",
    "templates/pages/feature_list.html": "",
    "templates/pages/launch_page.html": "",

    "scripts/pipeline.py": "print('pipeline placeholder')",

    "seo/sitemap_builder.py": "",
    "seo/internal_links.py": "",
    "seo/schema_markup.py": "",

    "config/site_config.yaml": "site: phoneblogs",
    "config/generation_rules.yaml": "",
    "config/niches.yaml": "",

    "README.md": "# PhoneBlogs\nProgrammatic SEO tech site"
}

# Create directories
for d in dirs:
    Path(d).mkdir(parents=True, exist_ok=True)

# Create files
for path, content in files.items():
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)

    if not p.exists():
        with open(p, "w") as f:
            f.write(content)

print("Repository structure created successfully.")
