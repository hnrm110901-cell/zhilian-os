"""
FL Minimum Viable Validation - 联邦BOM学习最小可行验证

Runs a real end-to-end federated BOM training round across 3 simulated test stores
and asserts the aggregated global model is correct.

Usage:
    cd apps/api-gateway/apps/api-gateway
    python scripts/validate_fl_bom.py
"""
import asyncio
import math
import sys
from datetime import datetime, timedelta
import random

# Make sure src is importable
sys.path.insert(0, ".")

from src.services.federated_bom_service import FederatedBOMService


# ── Test data generators ──────────────────────────────────────────────────────

def make_store_data(store_id: str, base_loss_rate: float, n: int = 60) -> list:
    """Generate n days of realistic BOM records for one store."""
    random.seed(hash(store_id))
    records = []
    for i in range(n):
        date = datetime(2025, 11, 1) + timedelta(days=i)
        purchase = random.uniform(80, 120)
        loss = purchase * base_loss_rate * random.uniform(0.8, 1.2)
        records.append({
            "date": date,
            "purchase_quantity": round(purchase, 2),
            "loss_quantity": round(loss, 2),
            "temperature": random.uniform(5, 15),   # winter
            "humidity": random.uniform(55, 75),
            "storage_days": random.randint(2, 5),
            "is_holiday": (date.weekday() >= 5),
        })
    return records


# ── Validation helpers ────────────────────────────────────────────────────────

PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"
failures = []


def check(label: str, condition: bool, detail: str = ""):
    status = PASS if condition else FAIL
    print(f"  [{status}] {label}" + (f"  ({detail})" if detail else ""))
    if not condition:
        failures.append(label)


# ── Main validation ───────────────────────────────────────────────────────────

async def run():
    print("\n=== FL BOM Minimum Viable Validation ===\n")

    svc = FederatedBOMService()
    ingredient_id = "chili_001"

    # --- Step 1: train local models on 3 stores ---
    print("Step 1: Train local models (3 stores)")
    stores = {
        "store_shanghai_001": 0.08,   # 8% loss
        "store_beijing_002":  0.12,   # 12% loss
        "store_guangzhou_003": 0.06,  # 6% loss
    }
    updates = []
    for store_id, base_loss in stores.items():
        data = make_store_data(store_id, base_loss)
        update = await svc.train_local_model(store_id, ingredient_id, data)
        updates.append(update)

        check(
            f"{store_id}: update returned",
            update is not None,
        )
        check(
            f"{store_id}: has gradients",
            len(update.model_gradients) > 0,
            f"len={len(update.model_gradients)}",
        )
        check(
            f"{store_id}: local_samples > 0",
            update.local_samples > 0,
            f"n={update.local_samples}",
        )
        check(
            f"{store_id}: loss_rate in [0, 1]",
            0.0 <= update.local_loss_rate <= 1.0,
            f"{update.local_loss_rate:.4f}",
        )

    # --- Step 2: federated aggregation ---
    print("\nStep 2: Federated aggregation (FedAvg)")
    global_model = await svc.federated_aggregate(updates)

    check("global_model returned", bool(global_model))
    check("num_stores == 3", global_model.get("num_stores") == 3,
          str(global_model.get("num_stores")))
    check("total_samples > 0", global_model.get("total_samples", 0) > 0,
          str(global_model.get("total_samples")))

    agg_loss = global_model.get("loss_rate", -1)
    expected_approx = (0.08 + 0.12 + 0.06) / 3   # ~0.0867 (equal-weight approx)
    check(
        "aggregated loss_rate in plausible range [0.05, 0.15]",
        0.05 <= agg_loss <= 0.15,
        f"got {agg_loss:.4f}, expected ~{expected_approx:.4f}",
    )

    gradients = global_model.get("gradients", [])
    check("aggregated gradients non-empty", len(gradients) > 0)
    check("gradients are finite", all(math.isfinite(g) for g in gradients))

    # --- Step 3: prediction ---
    print("\nStep 3: Prediction from global model")
    pred = await svc.predict_loss_rate(
        ingredient_id=ingredient_id,
        season="winter",
        region="华东",
        temperature=8.0,
        humidity=65.0,
        storage_days=3,
    )
    check("prediction returned float", isinstance(pred, float))
    check("prediction in [0, 1]", 0.0 <= pred <= 1.0, f"{pred:.4f}")

    # --- Step 4: anomaly detection ---
    print("\nStep 4: Anomaly detection")
    # Normal store — should NOT be anomaly
    normal = await svc.detect_anomaly("store_normal", ingredient_id, agg_loss * 1.1)
    check("normal store: is_anomaly=False", not normal["is_anomaly"],
          f"deviation={normal['deviation']:.4f}")

    # Outlier store — should BE anomaly (3× global rate)
    outlier = await svc.detect_anomaly("store_outlier", ingredient_id, agg_loss * 3.5)
    check("outlier store: is_anomaly=True", outlier["is_anomaly"],
          f"deviation={outlier['deviation']:.4f}")

    # --- Step 5: cross-region knowledge sync ---
    print("\nStep 5: Cross-region knowledge sync")
    sync = await svc.sync_knowledge_across_regions("华东", "华南", ingredient_id)
    check("sync returned result", bool(sync))
    check("confidence decayed", sync["confidence"] < 0.8,
          f"{sync['confidence']:.3f}")

    # --- Step 6: model statistics ---
    print("\nStep 6: Model statistics")
    stats = svc.get_model_statistics()
    check("total_global_models == 1", stats["total_global_models"] == 1,
          str(stats["total_global_models"]))

    # ── Summary ──────────────────────────────────────────────────────────────
    print(f"\n{'='*40}")
    if failures:
        print(f"\033[31mFAILED\033[0m  {len(failures)} check(s):")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    else:
        print(f"\033[32mALL CHECKS PASSED\033[0m  (3 stores, FedAvg, predict, anomaly, sync)")
    print()


if __name__ == "__main__":
    asyncio.run(run())
