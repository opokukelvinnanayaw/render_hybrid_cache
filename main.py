"""
Main Gateway Entry Point for Render Hybrid Cache System
======================================================
Run this file directly: python main.py
Automatically connects to your live Firebase credentials and discovers all tables/collections!
"""

import sys
import os
import time
import json

# Ensure package root is in sys.path
sys.path.insert(0, os.path.dirname(__file__))

try:
    import firebase_admin  # type: ignore
    from firebase_admin import credentials, firestore  # type: ignore
except ImportError:
    firebase_admin = None  # type: ignore

from render_hybrid_cache import RenderHybridCache, hybrid_cache, BaaSCacheAdapter


def get_firebase_credentials():
    """Locates or interactively prompts user for Firebase Service Account SDK credentials."""
    if firebase_admin is None:
        print("[WARN] `firebase_admin` package not installed. Install via `pip install firebase-admin`")
        return None, None

    default_path = os.environ.get(
        "FIREBASE_SERVICE_ACCOUNT_PATH",
        os.path.abspath(os.path.join(os.path.dirname(__file__), "firebase-service-account.json"))
    )

    if os.path.exists(default_path):
        return credentials.Certificate(default_path), default_path

    # Check common locations in parent workspace
    workspace_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    for candidate in [
        os.path.join(workspace_root, "firebase-service-account.json"),
        os.path.join(workspace_root, "kwabz-whatsapp-bot", "firebase-service-account.json"),
    ]:
        if os.path.exists(candidate):
            return credentials.Certificate(candidate), candidate

    # Prompt user interactively
    print("\n" + "-" * 70)
    print("[INPUT REQUIRED] Firebase Service Account credentials not found.")
    print("Please enter your Firebase SDK setup info:")
    print("  1) Enter or drag-and-drop path to your `firebase-service-account.json` file")
    print("  2) OR paste raw JSON key content (starts with '{' and ends with '}')")
    print("  3) Press [ENTER] to skip and run in local diagnostic mode")
    print("-" * 70)

    try:
        user_input = input("Firebase SDK Credentials > ").strip()
    except (EOFError, KeyboardInterrupt):
        return None, None

    if not user_input:
        return None, None

    cleaned_input = user_input.strip('"\'')

    # Option 1: File Path
    if os.path.exists(cleaned_input):
        try:
            return credentials.Certificate(cleaned_input), cleaned_input
        except Exception as e:
            print(f"[ERROR] Could not load certificate from path '{cleaned_input}': {e}")
            return None, None

    # Option 2: Pasted Raw JSON
    if cleaned_input.startswith("{") and cleaned_input.endswith("}"):
        try:
            cred_dict = json.loads(cleaned_input)
            saved_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "firebase-service-account.json"))
            with open(saved_path, "w", encoding="utf-8") as f:
                json.dump(cred_dict, f, indent=2)
            print(f"[OK] Saved credentials to '{saved_path}'!")
            return credentials.Certificate(cred_dict), saved_path
        except Exception as e:
            print(f"[ERROR] Failed to parse pasted JSON credentials: {e}")
            return None, None

    print(f"[ERROR] Path '{cleaned_input}' does not exist and input is not valid JSON.")
    return None, None


def main():
    print("=" * 70)
    print("      RENDER HYBRID CACHING SYSTEM - FIREBASE GATEWAY INITIALIZING      ")
    print("=" * 70)

    cache = RenderHybridCache(l1_max_size=2000, l1_ttl=300)
    baas = BaaSCacheAdapter(cache_instance=cache)

    print("\n[OK] Tier 1 (L1 Memory LRU) & Tier 2 (Firebase / Memory Storage) Active.")
    print("[OK] SingleFlight Cache Stampede Guard Ready.")
    print("[OK] Tag Invalidation Engine Ready.")

    cred_cert, cred_path = get_firebase_credentials()

    # Connect to Firebase if credentials acquired
    if cred_cert is not None:
        print(f"\n[FIREBASE] Using credentials from: {cred_path}")
        if not firebase_admin._apps:
            firebase_admin.initialize_app(cred_cert)
        db = firestore.client()
        print("[FIREBASE] Connected successfully to Google Cloud Firestore!\n")

        print("[DISCOVERY] Querying Firestore schema to discover ALL tables/collections...")
        col_refs = list(db.collections())
        col_names = [c.id for c in col_refs]

        if not col_names:
            print("[INFO] No root collections found via schema introspection. Trying default list...")
            col_names = ["products", "users", "orders", "sellers", "bundles", "gigs", "blogs"]

        print(f"[FOUND] Discovered {len(col_names)} Firestore Collections/Tables:")
        for idx, name in enumerate(col_names, 1):
            print(f"   {idx}. Collection: '{name}'")

        print("\n" + "=" * 70)
        print("   EXECUTING HYBRID CACHING DEMO ON ALL FIREBASE TABLES   ")
        print("=" * 70)

        for col in col_names:
            def _fetch_table(c_name=col):
                # Stream all documents in the collection without limiting
                docs = db.collection(c_name).get()
                return [d.to_dict() for d in docs]

            # Fetch via hybrid cache
            t0 = time.time()
            res1 = baas.wrap_query(f"firestore:{col}", _fetch_table, ttl=300, tags=[col, "firebase"])
            dur1 = time.time() - t0

            # Cached fetch
            t0 = time.time()
            res2 = baas.wrap_query(f"firestore:{col}", _fetch_table, ttl=300, tags=[col, "firebase"])
            dur2 = time.time() - t0

            speedup = (dur1 / max(dur2, 0.0001))
            print(f" -> Table '{col}': {len(res1)} records | Fetch: {dur1:.4f}s | Cache Hit: {dur2:.4f}s ({speedup:.1f}x faster)")

    else:
        print("\n[INFO] Firebase service account not connected. Running internal diagnostic cache mode...")

    print("\nSystem Statistics:")
    print(cache.get_stats())
    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()

