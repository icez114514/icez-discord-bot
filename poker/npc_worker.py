"""Fixed inference worker. No configurable imports, model paths or executors."""

import hashlib
import importlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent / "vendor" / "fullhouse"
EXPECTED = {
    "deep_cfr_model.npz": "1102326b68da95564de147106612df71cb891b42f0726ba0212d3b9a5bcae295",
    "preflop_equity.npz": "6b3b74778854fcebcd3179753c0252392e5f4118e6b623375c98fafa372863b3",
}


def main():
    try:
        for name, digest in EXPECTED.items():
            if (
                hashlib.sha256((ROOT / "data" / name).read_bytes()).hexdigest()
                != digest
            ):
                raise RuntimeError("fixed_data_hash_mismatch")
        sys.path.insert(0, str(ROOT))
        eval7 = importlib.import_module("eval7")
        fixed = importlib.import_module("bot.bot")
        eval7.evaluate([eval7.Card(c) for c in ("As", "Kd", "Qh", "Jc", "Tc")])
        print(json.dumps({"ready": True}), flush=True)
    except Exception as error:
        print(json.dumps({"error": "npc_startup_" + type(error).__name__}), flush=True)
        return
    while True:
        line = sys.stdin.buffer.readline(65537)
        if not line:
            return
        if len(line) > 65536:
            return
        try:
            state = json.loads(line)
            # Keep upstream short-stack strategy and the same five-action conversion.
            # Bypass only decide()'s silent exception fallback.
            decision = fixed._push_fold(state) if state["street"] == "preflop" else None
            if decision is None:
                strategy = fixed._DEEP_CFR.get_strategy(state)
                strategy = fixed._apply_legal_mask(strategy, state)
                decision = fixed._to_engine_action(fixed._sample(strategy), state)
            print(json.dumps({"decision": decision}), flush=True)
        except Exception as error:
            # Never log state, cards, exception messages or arbitrary model output.
            print(
                json.dumps({"error": "npc_inference_" + type(error).__name__}),
                flush=True,
            )


if __name__ == "__main__":
    main()
