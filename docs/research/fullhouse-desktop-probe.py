"""Bounded desktop suitability probe; synthetic states, not strength evaluation."""
import os
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"
import sys, json, time, copy, hashlib
from pathlib import Path
ROOT = Path(os.environ.get("FULLHOUSE_REVIEW_ROOT", str(Path(__file__).resolve().parents[2] / "tmp/fullhouse-review-e504793"))).resolve()
if "--without-deps" not in sys.argv:
    sys.path.insert(0, str(ROOT / "deps"))
sys.path.insert(0, str(ROOT))
import numpy as np
import psutil
p = psutil.Process()
before = p.memory_info().rss
start = time.perf_counter()
from bot import bot
from bot.features import encode_state_dict, _compute_legal_mask
loaded_ms = (time.perf_counter() - start) * 1000
def state(n=6, street="preflop", chips=10000):
    board = {"preflop": [], "flop": ["2c","7d","Th"],
             "turn":["2c","7d","Th","Jc"], "river":["2c","7d","Th","Jc","Qs"]}[street]
    pre = street == "preflop"
    players = [{"seat":i,"stack":chips,"bet_this_street":0,"is_folded":False,"is_all_in":False} for i in range(n)]
    if pre:
        players[1 % n]["bet_this_street"] = 50
        players[(2 if n > 2 else 0)]["bet_this_street"] = 100
    return {"street":street,"your_cards":["As","Kd"],"community_cards":board,
            "players":players,"seat_to_act":0,"dealer":0,"button":0,
            "your_stack":chips,"your_bet_this_street":0,"pot":150 if pre else 600,
            "amount_owed":100 if pre else 0,"current_bet":100 if pre else 0,
            "min_raise_to":200 if pre else 100,"can_check":not pre,"action_log":[]}
if "--without-deps" in sys.argv:
    s = state(street="flop")
    try:
        bot._DEEP_CFR.get_strategy(s)
        underlying_error = None
    except Exception as exc:
        underlying_error = type(exc).__name__ + ": " + str(exc)
    result = {"underlying_error":underlying_error,"decide_returned":bot.decide(s)}
    (ROOT / "missing-dependency-result.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    print(json.dumps(result))
    raise SystemExit()
with np.load(ROOT / "data/deep_cfr_model.npz", allow_pickle=False) as model:
    arrays = {k: {"shape":list(model[k].shape),"dtype":str(model[k].dtype)} for k in model.files}
    model_nbytes = sum(model[k].nbytes for k in model.files)
    assert all(model[k].dtype.kind in "fiub" and np.isfinite(model[k]).all() for k in model.files)
fallbacks = [0]
original_fallback = bot._safe_default_action
def observed_fallback(s):
    fallbacks[0] += 1
    return original_fallback(s)
bot._safe_default_action = observed_fallback
cases = [state(n, street, chips) for n in range(2,7)
         for street in ["preflop","flop","turn","river"] for chips in [2000,10000,20000]]
checks = []
for s in cases:
    probs = bot._DEEP_CFR.get_strategy(s)
    _, legal = encode_state_dict(s)
    assert probs.shape == (5,) and np.isfinite(probs).all()
    assert np.all(probs >= 0) and abs(float(probs.sum()) - 1) < 1e-5
    assert np.all(probs[~legal] == 0)
    checks.append({"players":len(s["players"]),"street":s["street"],"stack":s["your_stack"],
                   "legal":legal.tolist(),"probs":probs.tolist(),"action":bot.decide(s)})
for i in range(100):
    bot.decide(cases[i % len(cases)])
durations=[]
start=time.perf_counter()
for i in range(3000):
    s=cases[i % len(cases)]
    t=time.perf_counter_ns()
    bot.decide(s)
    durations.append((time.perf_counter_ns()-t)/1e6)
elapsed=time.perf_counter()-start
raw=state(6,"preflop",400)
raw["your_cards"]=["As","Ah"]
raw.update(pot=30,amount_owed=20,current_bet=20,min_raise_to=40)
for player in raw["players"]:
    player["bet_this_street"] /= 5
normalized=copy.deepcopy(raw)
for field in ["pot","amount_owed","current_bet","min_raise_to","your_stack","your_bet_this_street"]:
    normalized[field] *= 5
for player in normalized["players"]:
    player["stack"] *= 5
    player["bet_this_street"] *= 5
normalization = {"raw_400_chips_20bb_push_fold":bot._push_fold(raw),
                 "normalized_2000_units_20bb_push_fold":bot._push_fold(normalized)}
s=state(6,"flop")
q=bot._DEEP_CFR.get_strategy(s)
private_changed=copy.deepcopy(s)
private_changed["deck"]=["Ac","Ad"]
for x in private_changed["players"]:
    x["hole_cards"]=["9c","9d"]
unchanged=bool(np.array_equal(q,bot._DEEP_CFR.get_strategy(private_changed)))
result={"commit":"e504793d480b1b975f25258d25939b45c6dbd5a4",
        "python":sys.version.split()[0],"numpy":np.__version__,"eval7":"0.1.11",
        "model_sha256":hashlib.sha256((ROOT/"data/deep_cfr_model.npz").read_bytes()).hexdigest(),
        "model_file_bytes":(ROOT/"data/deep_cfr_model.npz").stat().st_size,
        "model_array_bytes":model_nbytes,"arrays":arrays,"import_and_model_load_ms":loaded_ms,
        "rss_before_runtime_mib":before/2**20,"rss_after_mib":p.memory_info().rss/2**20,
        "synthetic_cases":len(cases),"timed_calls":3000,"elapsed_s":elapsed,
        "decision_ms":{k:float(np.percentile(durations,v)) for k,v in [("p50",50),("p95",95),("p99",99),("max",100)]},
        "fallback_count":fallbacks[0],"money_normalization":normalization,
        "extra_unknown_card_fields_ignored_in_one_case":unchanged,
        "limitations":["Windows desktop only, not Termux.","Synthetic states, no complete hands, winrate or equilibrium test.",
                       "One sequential process with BLAS threads=1; not five simultaneous tables.","No side-pot payout or authoritative engine test."]}
(ROOT/"desktop-probe-results.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
print(json.dumps({k:v for k,v in result.items() if k!="arrays"},indent=2))
