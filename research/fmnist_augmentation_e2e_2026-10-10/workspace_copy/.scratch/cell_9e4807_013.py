
import pandas as pd
import os

csv_files = {
    'seed42_noaug':  'data/metrics_seed42_noaug.csv',
    'seed42_aug':    'data/metrics_seed42_aug.csv',
    'seed123_noaug': 'data/metrics_seed123_noaug.csv',
    'seed123_aug':   'data/metrics_seed123_aug.csv',
}

all_ok = True
results = {}

for name, path in csv_files.items():
    print(f"\n{'='*60}\n{name}")
    with open(path) as f:
        lines = f.readlines()
    
    print(f"  Lines: {len(lines)} | Size: {os.path.getsize(path)} bytes")
    print(f"  Comment: {lines[0].rstrip()}")
    comment_ok = lines[0].startswith('#') and 'cuda' in lines[0].lower()
    print(f"  Comment has CUDA: {'OK' if comment_ok else 'FAIL'}")
    
    df = pd.read_csv(path, comment='#')
    n_rows = len(df)
    
    epoch_min = df['epoch'].min()
    epoch_max = df['epoch'].max()
    test_min  = df['test_acc'].min()
    test_max  = df['test_acc'].max()
    val_min   = df['val_acc'].min()
    has_nan   = df.isnull().any().any()
    
    print(f"  Rows (comment='#'): {n_rows} {'OK' if n_rows==30 else 'FAIL'}")
    print(f"  Epoch range: {epoch_min}..{epoch_max} {'OK' if epoch_min==1 and epoch_max==30 else 'FAIL'}")
    print(f"  test_acc range: [{test_min:.2f}, {test_max:.2f}] {'OK' if test_min>=50 and test_max<=99 else 'FAIL'}")
    print(f"  val_acc range:  [{val_min:.2f}, {df['val_acc'].max():.2f}] {'OK' if val_min>=50 else 'FAIL'}")
    print(f"  No NaN: {'OK' if not has_nan else 'FAIL'}")
    
    # Naive read
    df_n = pd.read_csv(path)
    print(f"  Rows (naive read): {len(df_n)} {'OK' if len(df_n)==30 else 'NOTE: '+str(len(df_n))}")
    
    # Non-empty line counts
    ne = [l for l in lines if l.strip()]
    print(f"  Non-empty lines: {len(ne)} | -1={len(ne)-1} | -2={len(ne)-2}")
    
    ep5  = df[df['epoch']==5]['test_acc'].values[0]
    ep30 = df[df['epoch']==30]['test_acc'].values[0]
    print(f"  Epoch-5  test_acc: {ep5:.2f}%")
    print(f"  Epoch-30 test_acc: {ep30:.2f}%")
    
    run_ok = (n_rows==30 and epoch_min==1 and epoch_max==30 and 
              test_min>=50 and test_max<=99 and not has_nan and comment_ok)
    print(f"  STATUS: {'PASS' if run_ok else 'FAIL'}")
    results[name] = {'ep5': ep5, 'ep30': ep30, 'rows': n_rows, 'ok': run_ok}
    all_ok = all_ok and run_ok

print(f"\n\nOVERALL CSV STATUS: {'ALL PASS' if all_ok else 'SOME FAILED'}")
