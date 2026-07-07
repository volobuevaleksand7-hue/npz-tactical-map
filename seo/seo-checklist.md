# NPZ Tactical Map — SEO Checklist

> Prepared 2026-07-07. All items are **pending** — do NOT deploy until reviewed.

---

## 🔴 Critical (blocks indexing / ranking)

### 1. Google Search Console verification
- **File:** `index.html` line 16
- **Current:** `<meta name="google-site-verification" content="GOOGLE_SEARCH_CONSOLE_CODE">`
- **Action:** Obtain real verification code from https://search.google.com/search-console
  - Add property → `npz-tactical-map.vercel.app`
  - Settings → Ownership verification → HTML tag method
  - Copy `content="..."` value and replace `GOOGLE_SEARCH_CONSOLE_CODE`
- **Status:** ⏳ TODO — owner must obtain code manually
- **Code comment left:** `<!-- TODO: Replace GOOGLE_SEARCH_CONSOLE_CODE with real GSC code -->`

### 2. cleanUrls: false → true in vercel.json
- **File:** `vercel.json` line 3
- **Current:** `"cleanUrls": false`
- **Change to:** `"cleanUrls": true`
- **Effect:** Vercel will strip `.html` extensions from URLs automatically
  - `/news/2026-07-07.html` → `/news/2026-07-07`
  - `/radar.html` → `/radar`
- **Note:** With `cleanUrls: true`, the manual rewrites in `vercel.json` lines 5–8
  (`/news` → `/news.html`, `/radar` → `/radar.html`, etc.) become **redundant** and
  can be removed to avoid conflicts. Vercel handles clean URL routing automatically
  when this flag is set. Remove:
  ```json
  "rewrites": [
    { "source": "/news", "destination": "/news.html" },
    { "source": "/radar", "destination": "/radar.html" },
    { "source": "/sources", "destination": "/sources.html" },
    { "source": "/news/:slug", "destination": "/news/:slug.html" }
  ]
  ```
- **Status:** ⏳ Pending

### 3. BreadcrumbList schema missing on all 54 article pages
- **Files:** All `news/*.html` (54 pages)
- **Current:** Each article has `NewsArticle` JSON-LD but NO `BreadcrumbList`
- **Template:** `seo/breadcrumb-template.json`
- **To inject per article:** Place a second `<script type="application/ld+json">` block
  immediately after the existing NewsArticle `<script>` in `<head>`:
  ```html
  <script type="application/ld+json">
  {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    "itemListElement": [
      {"@type": "ListItem", "position": 1, "name": "Главная", "item": "https://npz-tactical-map.vercel.app/"},
      {"@type": "ListItem", "position": 2, "name": "Новости", "item": "https://npz-tactical-map.vercel.app/news"},
      {"@type": "ListItem", "position": 3, "name": "Сводка за 7 июля 2026: ...", "item": "https://npz-tactical-map.vercel.app/news/2026-07-07"}
    ]
  }
  </script>
  ```
- **Automation:** Write a script (Python or JS) that:
  1. Reads each `news/*.html`
  2. Extracts the `<title>` or `og:title` for `ARTICLE_TITLE`
  3. Derives the slug from filename (e.g. `2026-07-07.html` → `2026-07-07`)
  4. Injects the BreadcrumbList JSON-LD after the existing NewsArticle `<script>` block
- **Status:** ⏳ Pending (all 54 pages)

---

## 🟡 Important (affects crawl quality)

### 4. Sitemap automation
- **Current:** Static `sitemap.xml` (405 lines, manually maintained)
- **Prepared:** `seo/generate-sitemap.py` — auto-generates from all `.html` files
- **Action:** Run `python3 seo/generate-sitemap.py` before each deploy, or integrate
  into CI/CD (Vercel Build Command)
- **Status:** ⏳ Script prepared, needs integration

### 5. Yandex.Webmaster verification
- **File:** `index.html` line 18
- **Current:** `<meta name="yandex-verification" content="3043c11e2e96ee23">` ✅ Already set
- **Yandex verification file:** `yandex_3043c11e2e96ee23.html` exists ✅
- **Status:** ✅ Done

### 6. Missing cover images for May–June 2026 articles (23 articles)
- **Problem:** 23 articles from May 2026 and early June 2026 lack dedicated OG cover images
- **Current fallback:** They reference `assets/cover-YYYY-MM-DD.png` which may not exist
- **Impact:** Social sharing cards show broken/missing images
- **Action:** Either generate covers for all articles or set a generic fallback OG image
- **Status:** ⏳ Pending

---

## 🟢 Recommended (best practices)

### 7. Add `<link rel="alternate" hreflang="ru">` to article `<head>` sections
- **Status:** ⏳ Pending — low priority since site is Russian-only

### 8. Ensure all article pages have proper `<title>` length (50–60 chars)
- **Status:** ⏳ Audit needed — some titles may be too long for SERP display

### 9. Add `robots.txt` noindex for non-public pages
- `dashboard/index.html` — internal, should probably be `noindex`
- `seo/meta-tags.html` — internal template
- `yandex_3043c11e2e96ee23.html` — verification file
- **Status:** ⏳ Pending

### 10. canonical URL audit
- All pages should have `<link rel="canonical">` pointing to the clean URL version
- After enabling `cleanUrls: true`, verify canonicals don't still point to `.html` URLs
- **Status:** ⏳ Pending post-deploy check

### 11. Page speed / Core Web Vitals
- Run Lighthouse audit after deploy
- Check that Leaflet tiles load efficiently (no CLS from map init)
- **Status:** ⏳ Pending

---

## Summary of prepared files

| File | Purpose | Status |
|------|---------|--------|
| `seo/generate-sitemap.py` | Auto-generate sitemap.xml from all .html files | ✅ Created |
| `seo/breadcrumb-template.json` | BreadcrumbList JSON-LD template for articles | ✅ Created |
| `seo/seo-checklist.md` | This checklist | ✅ Created |

## Pending manual actions

1. **Get GSC verification code** from Google Search Console → replace placeholder in `index.html`
2. **Set `cleanUrls: true`** in `vercel.json` (and remove redundant rewrites)
3. **Inject BreadcrumbList** into all 54 `news/*.html` pages
4. **Run `generate-sitemap.py`** and verify output before deploy
5. **Create cover images** for 23 articles missing dedicated covers
