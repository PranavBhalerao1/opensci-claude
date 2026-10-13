import ast, re

src = open("src/train.py").read()

# 1. Syntax
ast.parse(src)
print("1. Syntax: OK")

# 2. SmallCNN — two Conv blocks, two FC layers, no BatchNorm (functional)
tree = ast.parse(src)
for node in ast.walk(tree):
    if isinstance(node, ast.ClassDef) and node.name == "SmallCNN":
        class_src = ast.get_source_segment(src, node)
        conv_count = class_src.count("nn.Conv2d")
        fc_count   = class_src.count("nn.Linear")
        pool_count = class_src.count("nn.MaxPool2d")
        relu_count = class_src.count("nn.ReLU")
        drop_count = class_src.count("nn.Dropout")
        bn_count   = class_src.count("BatchNorm")
        print(f"2. SmallCNN: Conv2d={conv_count}(need 2)  Linear={fc_count}(need 2)  "
              f"MaxPool2d={pool_count}(need 2)  ReLU={relu_count}(need 3)  "
              f"Dropout={drop_count}(need 1)  BatchNorm={bn_count}(need 0)")
        assert conv_count == 2 and fc_count == 2 and bn_count == 0

# 3. Argparse flags
for flag in ["--seed", "--augment", "--epochs", "--data_dir", "--out_dir"]:
    assert flag in src, f"Missing: {flag}"
print("3. Argparse flags: OK")

# 4. Seed fixing
for sym in ["random.seed(seed)", "np.random.seed(seed)",
            "torch.manual_seed(seed)", "torch.cuda.manual_seed_all(seed)",
            "cudnn.deterministic = True"]:
    assert sym in src, f"Missing seed call: {sym}"
print("4. Seed fixing: OK")

# 5. CSV with comment header
assert "# seed=" in src and "started=" in src
print("5. CSV comment header: OK")

# 6. Checkpoint naming pattern
assert "checkpoint_seed" in src and "_ep" in src
print("6. Checkpoint naming: OK")

# 7. Checkpoint epochs {5,10,20,30}
assert "{5, 10, 20, 30}" in src or "5, 10, 20, 30" in src
print("7. Checkpoint epochs {{5,10,20,30}}: OK")

# 8. Train/val split 55k/5k
assert "55_000" in src or "55000" in src
print("8. 55k/5k split: OK")

# 9. Adam lr and weight_decay
assert "lr=0.001" in src and "weight_decay=1e-4" in src
print("9. Optimizer (Adam lr=0.001 wd=1e-4): OK")

# 10. device = cuda if available else cpu
assert "cuda" in src and "cpu" in src
print("10. Device selection: OK")

print("\n=== All structural checks PASSED ===")
