"""Analysis of the decay-clock grid: event statistics, clock collapse, out-of-sample
prediction of grokking time from a critical cumulative shrinkage B*, learning-rate
effects at fixed eta*lambda, and figures. Writes results/ and figures/."""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).parent
OUT, FIG = ROOT / "results", ROOT / "figures"
OUT.mkdir(exist_ok=True)
FIG.mkdir(exist_ok=True)
rng = np.random.default_rng(0)

SCHED = ["const0.5", "const1.0", "const2.0", "const4.0", "early", "late", "ramp"]  # eta = 1e-3
LR = ["lr2", "lrhalf"]  # same eta*lambda as const1.0, different eta
LABEL = {"const0.5": "λ=0.5", "const1.0": "λ=1", "const2.0": "λ=2", "const4.0": "λ=4", "early": "early",
         "late": "late", "ramp": "ramp", "lr2": "2η, λ/2", "lrhalf": "η/2, 2λ", "nowd": "no decay"}
TASKS = {"add": "addition", "sub": "subtraction"}


def load():
    runs = []
    for f in sorted((ROOT / "grid").glob("*/summary.json")):
        s = json.loads(f.read_text())
        c = np.load(f.parent / "curves.npz")
        s["curves"] = {k: c[k] for k in c.files}
        runs.append(s)
    return runs


def boot_ci(x, fn=np.mean, n=10000):
    x = np.asarray(x, float)
    stats = [fn(rng.choice(x, len(x))) for _ in range(n)]
    return float(np.percentile(stats, 2.5)), float(np.percentile(stats, 97.5))


def eta_sq(groups):
    """Share of variance explained by condition (one-way ANOVA effect size)."""
    allv = np.concatenate(groups)
    grand = allv.mean()
    ss_between = sum(len(g) * (g.mean() - grand) ** 2 for g in groups)
    ss_total = ((allv - grand) ** 2).sum()
    return float(ss_between / ss_total)


def main():
    runs = load()
    by = {}
    for r in runs:
        by.setdefault((r["task"], r["cond"]), []).append(r)

    # 1 · Per-condition event table
    table = []
    for task in TASKS:
        for cond in SCHED + LR + ["nowd"]:
            rs = by.get((task, cond), [])
            gen = [r for r in rs if r["t_gen"] is not None]
            row = {"task": task, "cond": cond, "n": len(rs), "n_grokked": len(gen)}
            if gen:
                t = np.array([r["t_gen"] for r in gen], float)
                b = np.array([r["B_gen"] for r in gen], float)
                bd = np.array([r["B_gen"] - r["B_mem"] for r in gen], float)
                row.update({"t_gen_mean": t.mean(), "t_gen_sd": t.std(ddof=1) if len(t) > 1 else 0.0,
                            "B_gen_mean": b.mean(), "B_gen_sd": b.std(ddof=1) if len(b) > 1 else 0.0,
                            "B_gen_ci": boot_ci(b), "t_gen_ci": boot_ci(t),
                            "dB_post_mem_mean": bd.mean(),
                            "t_mem_mean": float(np.mean([r["t_mem"] for r in gen]))})
            table.append(row)

    # 2 · Clock comparison across schedules at fixed eta (log scale; lower dispersion = better clock)
    clock = {}
    for task in TASKS:
        gs_t, gs_b = [], []
        for cond in SCHED:
            gen = [r for r in by.get((task, cond), []) if r["t_gen"] is not None]
            if len(gen) >= 2:
                gs_t.append(np.log([r["t_gen"] for r in gen]))
                gs_b.append(np.log([r["B_gen"] for r in gen]))
        pooled_t, pooled_b = np.concatenate(gs_t), np.concatenate(gs_b)
        # Bootstrap the ratio of across-run SDs (resample runs within condition).
        ratios = []
        for _ in range(5000):
            rt = np.concatenate([rng.choice(g, len(g)) for g in gs_t])
            rb = np.concatenate([rng.choice(g, len(g)) for g in gs_b])
            ratios.append(rt.std() / rb.std())
        clock[task] = {
            "conditions": len(gs_t), "runs": int(len(pooled_t)),
            "sd_log_step": float(pooled_t.std()), "sd_log_B": float(pooled_b.std()),
            "sd_ratio_step_over_B": float(pooled_t.std() / pooled_b.std()),
            "sd_ratio_ci": (float(np.percentile(ratios, 2.5)), float(np.percentile(ratios, 97.5))),
            "eta2_condition_on_log_step": eta_sq(gs_t), "eta2_condition_on_log_B": eta_sq(gs_b),
        }

    # 3 · Out-of-sample prediction: B* from const1.0 only, predict t_gen for other schedules
    pred = {}
    for task in TASKS:
        ref = [r["B_gen"] for r in by.get((task, "const1.0"), []) if r["B_gen"] is not None]
        b_star = float(np.median(ref))
        errs, rows = [], []
        for cond in [c for c in SCHED if c != "const1.0"] + LR:
            for r in by.get((task, cond), []):
                B = r["curves"]["B"]
                steps = r["curves"]["step"]
                # First evaluation step where cumulative shrinkage reaches B*.
                idx = np.searchsorted(B, b_star)
                t_pred = int(steps[idx]) if idx < len(steps) else None
                rows.append({"cond": cond, "seed": r["seed"], "t_gen": r["t_gen"], "t_pred": t_pred})
                if r["t_gen"] is not None and t_pred is not None and cond in SCHED:
                    errs.append(abs(np.log(t_pred / r["t_gen"])))
                elif (r["t_gen"] is None) != (t_pred is None) and cond in SCHED:
                    errs.append(np.nan)  # grokked but not predicted, or predicted but not grokked
        e = np.array(errs, float)
        ok = e[~np.isnan(e)]
        # Baseline: step clock, predicting every schedule groks at const1.0's median step.
        t_ref = float(np.median([r["t_gen"] for r in by.get((task, "const1.0"), []) if r["t_gen"]]))
        base = [abs(np.log(t_ref / r["t_gen"])) for c in SCHED if c != "const1.0"
                for r in by.get((task, c), []) if r["t_gen"]]
        pred[task] = {
            "B_star": b_star, "n_pred": int(len(e)), "n_mismatch_grok_status": int(np.isnan(e).sum()),
            "median_abs_log_error_Bclock": float(np.median(ok)) if len(ok) else None,
            "median_abs_pct_error_Bclock": float(100 * (np.exp(np.median(ok)) - 1)) if len(ok) else None,
            "median_abs_log_error_stepclock": float(np.median(base)) if base else None,
            "median_abs_pct_error_stepclock": float(100 * (np.exp(np.median(base)) - 1)) if base else None,
            "rows": rows,
        }

    # 4 · Learning rate at fixed eta*lambda: B_gen relative to const1.0
    lr_effect = {}
    for task in TASKS:
        base = np.array([r["B_gen"] for r in by.get((task, "const1.0"), []) if r["B_gen"]], float)
        for cond in LR:
            x = np.array([r["B_gen"] for r in by.get((task, cond), []) if r["B_gen"]], float)
            if len(x) and len(base):
                diffs = [rng.choice(x, len(x)).mean() / rng.choice(base, len(base)).mean() for _ in range(10000)]
                perm = np.concatenate([x, base])
                obs = x.mean() - base.mean()
                null = []
                for _ in range(10000):
                    rng.shuffle(perm)
                    null.append(perm[:len(x)].mean() - perm[len(x):].mean())
                lr_effect[f"{task}:{cond}"] = {
                    "ratio_B_gen_vs_const1": float(x.mean() / base.mean()),
                    "ratio_ci": (float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5))),
                    "perm_p": float((np.abs(null) >= abs(obs)).mean()), "n": int(len(x)), "n_ref": int(len(base))}

    results = {"table": table, "clock": clock, "prediction": {k: {kk: vv for kk, vv in v.items() if kk != "rows"}
                                                            for k, v in pred.items()},
               "lr_effect": lr_effect, "n_runs": len(runs)}
    (OUT / "results.json").write_text(json.dumps(results, indent=2, default=float))
    (OUT / "prediction_rows.json").write_text(json.dumps(pred, indent=1, default=float))

    # Figures ------------------------------------------------------------
    colors = dict(zip(SCHED + LR + ["nowd"], plt.cm.tab10(np.linspace(0, 1, 10))))
    for task, name in TASKS.items():
        fig, ax = plt.subplots(1, 2, figsize=(11, 4), sharey=True)
        for cond in SCHED + ["nowd"]:
            for i, r in enumerate(by.get((task, cond), [])[:3]):
                c = r["curves"]
                kw = dict(color=colors[cond], alpha=0.8, lw=1.2, label=LABEL[cond] if i == 0 else None)
                ax[0].plot(c["step"], c["test_acc"], **kw)
                ax[1].plot(c["B"], c["test_acc"], **kw)
        ax[0].set_xlabel("training step")
        ax[1].set_xlabel("cumulative weight-decay shrinkage  B = Σ −log(1−ηλ)")
        ax[1].set_xlim(0, 60)
        ax[0].set_ylabel("test accuracy")
        ax[0].legend(fontsize=8, ncol=2)
        fig.suptitle(f"Grokking curves ({name}): steps vs. the shrinkage clock")
        fig.tight_layout()
        fig.savefig(FIG / f"fig1_collapse_{task}.png", dpi=200)
        plt.close(fig)

    fig, ax = plt.subplots(1, 2, figsize=(11, 4))
    for j, (task, name) in enumerate(TASKS.items()):
        for cond in SCHED + LR:
            gen = [r for r in by.get((task, cond), []) if r["t_gen"]]
            if gen:
                ax[j].scatter([r["t_gen"] for r in gen], [r["B_gen"] for r in gen], color=colors[cond],
                              label=LABEL[cond], s=22, marker="^" if cond in LR else "o")
        ax[j].axhline(pred[task]["B_star"], color="k", ls="--", lw=1, label="B* (from λ=1)")
        ax[j].set_xscale("log")
        ax[j].set_xlabel("grokking step (log)")
        ax[j].set_ylabel("B at grokking")
        ax[j].set_title(name)
    ax[0].legend(fontsize=7, ncol=2)
    fig.tight_layout()
    fig.savefig(FIG / "fig2_step_vs_B.png", dpi=200)
    plt.close(fig)

    fig, ax = plt.subplots(1, 2, figsize=(11, 4))
    for j, (task, name) in enumerate(TASKS.items()):
        pts = [(r["t_gen"], r["t_pred"], r["cond"]) for r in pred[task]["rows"] if r["t_gen"] and r["t_pred"]]
        for tg, tp, cond in pts:
            ax[j].scatter(tp, tg, color=colors[cond], s=20, marker="^" if cond in LR else "o")
        lim = [5e3, 6e4]
        ax[j].plot(lim, lim, "k--", lw=1)
        ax[j].set_xscale("log")
        ax[j].set_yscale("log")
        ax[j].set_xlabel("predicted grokking step (B* from λ=1 only)")
        ax[j].set_ylabel("observed grokking step")
        ax[j].set_title(name)
    fig.tight_layout()
    fig.savefig(FIG / "fig3_prediction.png", dpi=200)
    plt.close(fig)
    print(json.dumps({k: v for k, v in results.items() if k != "table"}, indent=1, default=float))


if __name__ == "__main__":
    main()
