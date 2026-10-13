import ast, sys
src = open("src/train.py").read()
tree = ast.parse(src)
print("AST parse: OK")

# Check class SmallCNN is present and has no BatchNorm
lines = src.split("\n")
in_smallcnn = False
bn_lines = []
for i, ln in enumerate(lines, 1):
    if "class SmallCNN" in ln:
        in_smallcnn = True
    if in_smallcnn and ("BatchNorm" in ln or "batch_norm" in ln.lower()):
        bn_lines.append((i, ln))

print(f"SmallCNN found: {any('class SmallCNN' in l for l in lines)}")
print(f"BatchNorm occurrences inside SmallCNN: {bn_lines}")

# Check argparse flags
for flag in ["--seed", "--augment", "--epochs", "--data_dir", "--out_dir"]:
    present = any(flag in l for l in lines)
    print(f"  {flag}: {'FOUND' if present else 'MISSING'}")

# Check checkpoint epoch set
ck = any("5, 10, 20, 30" in l or "{5, 10, 20, 30}" in l for l in lines)
print(f"CHECKPOINT_EPOCHS {{5,10,20,30}}: {'FOUND' if ck else 'MISSING'}")

# Check seed-fixing calls
for call in ["random.seed", "np.random.seed", "torch.manual_seed",
             "torch.cuda.manual_seed_all", "cudnn.deterministic"]:
    present = any(call in l for l in lines)
    print(f"  {call}: {'FOUND' if present else 'MISSING'}")
