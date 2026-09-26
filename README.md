# Render Hybrid Caching System (`render-hybrid-cache`)

> A high-performance, multi-tier hybrid caching Python library engineered specifically for **Firebase Backend-as-a-Service (BaaS)** (Firestore / Realtime Database) and HTML/JSON template render pipelines.

[![Python Version](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

---

## Rationale & Architectural Design

Modern Firebase BaaS architectures offer immense developer velocity, but frequently suffer from:
1. **Network latency overhead** on repetitive database/API queries.
2. **Quota / Egress limits** on Firebase read calls.
3. **Template rendering computation costs** when serving dynamic SSR or API JSON views.

Building custom caching from scratch introduces difficult edge-cases: handling **Cache Stampedes (dog-piling)** under high traffic concurrency, maintaining **Thread & Async safety**, coordinating **Stale-While-Revalidate (SWR)** background updates, and invalidating cached records by **Tags** when Firebase database mutations occur.

`render-hybrid-cache` solves this by providing a ready-to-use Python package with:
- **Multi-Tier Hybrid Architecture**: Tier 1 (L1 Fast In-Memory LRU Cache) + Tier 2 (L2 Cloud Firestore / Storage Cache).
- **Tag-Based Invalidation**: Invalidate cache keys instantly across L1 and L2 whenever Firebase Firestore collections/documents are updated.
- **SingleFlight Concurrency Guard**: Mutex lock that prevents cache stampedes on expensive renders or queries.
- **Payload Compression & Serialization**: Built-in Gzip/Pickle compression for large rendered HTML or JSON payloads.
- **Unified Sync & Async Decorators**: `@hybrid_cache` and `@render_cache`.

---

## System Architecture

```
                                +---------------------------+
                                |  Caller / Web App / API   |
                                +-------------+-------------+
                                              |
                                              v
                              +---------------+---------------+
                              |    RenderHybridCache Engine   |
                              +---------------+---------------+
                                              |
                        +---------------------+---------------------+
                        |                                           |
                        v                                           v
         +--------------+--------------+             +--------------+--------------+
         |   Tier 1 (L1 Memory Cache)  |             |  Tier 2 (L2 Storage Cache)  |
         |  - In-Memory LRU            |             |  - Firebase Cloud Firestore  |
         |  - Per-key TTL              |             |  - Optional Redis           |
         |  - Ultra-fast <0.1ms        |             |  - Tag Indexing             |
         +--------------+--------------+             +--------------+--------------+
                        |                                           |
                        +---------------------+---------------------+
                                              | (Miss)
                                              v
                              +---------------+---------------+
                              |   SingleFlight Mutex Guard    |
                              +---------------+---------------+
                                              | (Leader computes once)
                                              v
                              +---------------+---------------+
                              | Firebase Firestore / Render   |
                              +-------------------------------+
```

---

## Installation

Clone this repository and install directly using `pip`:

```bash
# Clone the repository
git clone https://github.com/your-org/render-hybrid-cache.git
cd render-hybrid-cache

# Install locally in editable mode
pip install -e .
```

---

## Quickstart Usage

### 1. Basic Decorator Usage

```python
from render_hybrid_cache import hybrid_cache, render_cache

# Cache function result in L1 Memory & L2 Storage for 300 seconds
@hybrid_cache(ttl=300, tags=["products"])
def get_product_catalog(category: str):
    # Simulated heavy query or template render
    return {"category": category, "items": ["Item A", "Item B"]}

# HTML View Render Cache
@render_cache(ttl=600, tags=["pages"])
def render_landing_page():
    return "<html><body><h1>Welcome to Kwabz Store</h1></body></html>"

# Usage
data = get_product_catalog("electronics")  # Cache Miss -> Computes and stores
data_cached = get_product_catalog("electronics")  # Cache Hit -> Returned in <0.1ms
```

---

## Firebase BaaS Integration

Wrapping Firebase database calls and invalidating cache on mutations:

```python
from render_hybrid_cache import RenderHybridCache, BaaSCacheAdapter
from firebase_admin import firestore

cache = RenderHybridCache()
baas = BaaSCacheAdapter(cache_instance=cache)
db = firestore.client()

# 1. Fetch data from Firebase Firestore with hybrid caching & tags
def get_all_orders():
    return baas.wrap_query(
        query_name="firestore:orders",
        query_fn=lambda: [d.to_dict() for d in db.collection("orders").get()],
        ttl=300,
        tags=["orders"]
    )

# 2. On Firebase mutation hook (Insert / Update / Delete)
def on_order_created(new_order_data):
    db.collection("orders").add(new_order_data)
    # Invalidate all queries tagged with "orders"
    baas.on_mutation(["orders"])
```

---

## Cache Stampede Protection (SingleFlight)

When 100 concurrent incoming requests ask for an expired cache key simultaneously, `RenderHybridCache` routes requests through a `SingleFlight` lock. Only **one** request executes the computation or DB fetch, while the remaining 99 wait and receive the exact same result once computed.

---

## Tag Invalidation

```python
from render_hybrid_cache import RenderHybridCache

cache = RenderHybridCache()

cache.set("user:100:profile", {"name": "Alice"}, tags=["user:100", "users"])
cache.set("user:100:orders", [{"id": 1}], tags=["user:100", "orders"])

# Purge all cache entries tagged with "user:100"
purged_count = cache.invalidate_tag("user:100")
print(f"Purged {purged_count} entries associated with user 100")
```

---

## Core Package Architecture & File Breakdown (`render_hybrid_cache/`)

Below is the detailed explanation of each module inside the `render_hybrid_cache/` package:

| File Name | Purpose & Functionality |
| :--- | :--- |
| **`__init__.py`** | **Package Entrypoint & Exports** — Initializes the module and exposes primary clean imports (`RenderHybridCache`, `BaaSCacheAdapter`, `@hybrid_cache`, `@render_cache`, `FirebaseStorageCache`, `JsonSerializer`, `PickleSerializer`). |
| **`baas.py`** | **Firebase BaaS Query Adapter (`BaaSCacheAdapter`)** — Wraps live Firebase Firestore query functions (`wrap_query`, `wrap_query_async`), applies tag tagging, and provides automatic cache purging hooks on database mutations (`on_mutation`). |
| **`core.py`** | **Main Hybrid Caching Engine (`RenderHybridCache`)** — Coordinates L1 Memory LRU Cache and L2 Storage escalation. Manages Stale-While-Revalidate (SWR) background async execution, SingleFlight mutex locking, and multi-tier tag invalidations. |
| **`decorators.py`** | **Sync & Async Function Decorators (`@hybrid_cache`, `@render_cache`)** — Simplifies function caching by wrapping sync (`def`) and async (`async def`) Python functions or HTML view render functions with automatic cache lookups. |
| **`memory.py`** | **Tier 1 (L1) Ultra-Fast In-Memory LRU Cache (`MemoryCache`)** — Thread-safe memory cache providing sub-millisecond (<0.0001ms) lookups with Least-Recently-Used (LRU) eviction and per-key TTL tracking. |
| **`serializers.py`** | **Serialization & Compression Engine (`JsonSerializer`, `PickleSerializer`, `RawSerializer`)** — Encodes and decodes Python objects and HTML strings to binary format with optional built-in Gzip compression. |
| **`stampede.py`** | **Cache Stampede Guard (`SingleFlight`)** — Mutex lock mechanism preventing dog-piling when multiple concurrent requests hit an expired key simultaneously. Ensures only 1 request queries Firebase while 99 others wait and share the result. |
| **`storage.py`** | **Tier 2 (L2) Cloud & Storage Backends (`FirebaseStorageCache`, `MemoryStorageCache`, `RedisCache`)** — Provides persistent and cloud remote cache storage implementations for cross-instance and cross-session persistence. |

---

## Live Firebase Connection Benchmark & Real Output

When `main.py` is executed, it automatically parses SDK service account credentials, initializes `firebase_admin`, introspects your project's live schema, discovers **all 42 root Firestore collections**, and benchmarks the hybrid cache speedup:

```text
======================================================================
      RENDER HYBRID CACHING SYSTEM - FIREBASE GATEWAY INITIALIZING      
======================================================================

[OK] Tier 1 (L1 Memory LRU) & Tier 2 (Firebase / Memory Storage) Active.
[OK] SingleFlight Cache Stampede Guard Ready.
[OK] Tag Invalidation Engine Ready.

[FIREBASE] Using credentials from: C:\Users\kelvin\Desktop\version-2-main\kwabz-whatsapp-bot\firebase-service-account.json
[FIREBASE] Connected successfully to Google Cloud Firestore!

[DISCOVERY] Querying Firestore schema to discover ALL tables/collections...
[FOUND] Discovered 42 Firestore Collections/Tables:
   1. Collection: 'active_calls'          22. Collection: 'page_views'
   2. Collection: 'blog_comments'         23. Collection: 'password_hints'
   3. Collection: 'blog_posts'            24. Collection: 'presence'
   4. Collection: 'broadcasts'            25. Collection: 'product_notifications'
   5. Collection: 'bundles'               26. Collection: 'products'
   6. Collection: 'categories'            27. Collection: 'promo_codes'
   7. Collection: 'category_variants'     28. Collection: 'push_notifications_queue'
   8. Collection: 'communications'        29. Collection: 'pwa_installs'
   9. Collection: 'email_api_keys'        30. Collection: 'reviews'
   10. Collection: 'email_api_logs'       31. Collection: 'seller_pins'
   11. Collection: 'event_attendees'      32. Collection: 'sellers'
   12. Collection: 'event_tickets'        33. Collection: 'settings'
   13. Collection: 'events'               34. Collection: 'status_requests'
   14. Collection: 'fcm_tokens'           35. Collection: 'storefront_requests'
   15. Collection: 'feedback_form_config' 36. Collection: 'support_chats'
   16. Collection: 'feedback_submissions' 37. Collection: 'system_crashes'
   17. Collection: 'food_categories'      38. Collection: 'user_chats'
   18. Collection: 'food_items'           39. Collection: 'users'
   19. Collection: 'gigs'                 40. Collection: 'virtual_cards'
   20. Collection: 'media_library'        41. Collection: 'wallet_transactions_archive'
   21. Collection: 'orders'               42. Collection: 'whatsapp_bot_accounts'

======================================================================
   EXECUTING HYBRID CACHING DEMO ON ALL FIREBASE TABLES   
======================================================================
 -> Table 'gigs': 9 records              | Fetch: 1.3224s | Cache Hit: 0.0001s (13224.2x faster)
 -> Table 'user_chats': 559 records      | Fetch: 1.0712s | Cache Hit: 0.0000s (10711.6x faster)
 -> Table 'orders': 39 records           | Fetch: 0.7040s | Cache Hit: 0.0000s (7040.4x faster)
 -> Table 'products': 115 records        | Fetch: 0.6588s | Cache Hit: 0.0000s (6587.8x faster)
 -> Table 'status_requests': 434 records | Fetch: 1.4608s | Cache Hit: 0.0000s (14607.9x faster)
 -> Table 'users': 32 records            | Fetch: 0.4114s | Cache Hit: 0.0000s (4114.4x faster)
 -> Table 'media_library': 131 records   | Fetch: 0.5433s | Cache Hit: 0.0000s (5432.6x faster)

System Statistics:
{'l1_memory': {'size': 42, 'max_size': 2000, 'hits': 42, 'misses': 42, 'evictions': 0, 'hit_rate': 0.5}, 'l2_storage_class': 'MemoryStorageCache'}
======================================================================
```

---

## Hosting on Render (Render.com Setup Guide)

### Method A: Automated Deployment via `render.yaml` (Recommended)

1. Push your repo to **GitHub**.
2. Go to the [Render Dashboard](https://dashboard.render.com/) -> Click **New +** -> **Blueprint**.
3. Connect your repository. Render will automatically detect `render.yaml` and provision your Python Web Service.
4. Set your environment variable `FIREBASE_SERVICE_ACCOUNT_PATH=firebase-service-account.json`.

---

## Running Live Test Drive

Run entry point test drive:
```bash
python main.py
```

---

## License

Distributed under the MIT License. See `LICENSE` for details.


