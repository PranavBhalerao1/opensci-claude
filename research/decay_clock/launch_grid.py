"""Launch the main grid on Modal: 10 conditions x 2 tasks x 8 seeds, 8 runs per L4."""
import json, sys
from pathlib import Path
sys.path.insert(0, "/Users/akshatsg/Documents/kairo/backend")
from app.execution import modal_runner as mr

PID = sys.argv[1]
T = 50000
CONDS = ["const0.5", "const1.0", "const2.0", "const4.0", "early", "late", "ramp", "lr2", "lrhalf", "nowd"]
runs = [(task, c, s) for task in ("add", "sub") for c in CONDS for s in range(8) if not (c == "nowd" and s >= 4)]
jobs, chunk = [], 8
for i in range(0, len(runs), chunk):
    group = runs[i:i + chunk]
    cmd = " & ".join(f"python grok.py {t}_{c}_s{s} {t} {c} {s} {T} grid" for t, c, s in group) + " & wait"
    jobs.append({"name": f"grid_{i // chunk:02d}", "command": cmd})
print(len(runs), "runs in", len(jobs), "jobs", flush=True)
res = mr.run_jobs(PID, Path(__file__).parent, jobs, "L4", 3600, ["torch", "numpy"], cpu=8, memory_gib=16)
print(json.dumps([{k: j[k] for k in ("name", "exit_code", "seconds", "cost")} for j in res["jobs"]]))
print("synced", res["files_synced_back"])
