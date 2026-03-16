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
"logs",

]

files = {
"site/index.html": "PhoneBlogs",
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

"scripts/scrape/phones_scraper.py": "# TODO scraper",
"scripts/scrape/gpu_scraper.py": "# TODO scraper",
"scripts/scrape/laptop_scraper.py": "# TODO scraper",

"scripts/processors/normalize_data.py": "# normalize data",
"scripts/processors/ranking_engine.py": "# ranking logic",
"scripts/processors/comparison_builder.py": "# build comparisons",

"scripts/generators/device_page_generator.py": "# generate device pages",
"scripts/generators/comparison_generator.py": "# generate comparison pages",
"scripts/generators/feature_page_generator.py": "# generate feature pages",
"scripts/generators/price_page_generator.py": "# generate price pages",
"scripts/generators/launch_page_generator.py": "# generate launch pages",

"scripts/pipeline.py": "print('pipeline placeholder')",

"seo/sitemap_builder.py": "# build sitemap",
"seo/internal_links.py": "# internal linking engine",
"seo/schema_markup.py": "# schema generator",

"config/site_config.yaml": "site: phoneblogs",
"config/generation_rules.yaml": "",
"config/niches.yaml": "",

"README.md": "# PhoneBlogs\nProgrammatic SEO tech site"

}

for d in dirs:
Path(d).mkdir(parents=True, exist_ok=True)

for f, content in files.items():
p = Path(f)
p.parent.mkdir(parents=True, exist_ok=True)
if not p.exists():
with open(p, "w") as fp:
fp.write(content)

print("Repo structure created.")
