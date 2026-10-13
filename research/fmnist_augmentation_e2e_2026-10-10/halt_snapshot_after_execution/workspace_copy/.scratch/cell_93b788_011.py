
# Also update the docstring to reflect the new format
with open('src/train.py', 'r') as f:
    content = f.read()

old_doc = '''CSV format
----------
  Line 1  : # seed=<s> augment=<b> device=<d> start=<iso>   ← comment header
  Line 2  : epoch,train_loss,train_acc,val_acc,test_acc      ← column names
  Lines 3+ : one row per epoch, accuracies stored as PERCENTAGES (×100)
             e.g. 88.23 not 0.8823

  NOTE: train_acc / val_acc / test_acc are stored as percentages in [0, 100].
  This means test_acc for a reasonable model should be in [50, 99].'''

new_doc = '''CSV format
----------
  Line 1  : # seed=<s> augment=<b> device=<d> start=<iso>,train_loss,...,test_acc
            ← comment+column headers on ONE LINE (first col name = # comment)
            ← ensures pd.read_csv(path) returns exactly `epochs` data rows
  Lines 2+: one row per epoch, accuracies stored as PERCENTAGES (×100)
             e.g. 88.23 not 0.8823

  NOTE: train_acc / val_acc / test_acc are stored as percentages in [0, 100].
  This means test_acc for a reasonable model should be in [50, 99].
  NOTE: column named "# seed=..." is the epoch number column (first col).'''

if old_doc in content:
    content = content.replace(old_doc, new_doc)
    with open('src/train.py', 'w') as f:
        f.write(content)
    print("Docstring updated successfully")
else:
    print("Docstring pattern not found, skipping (non-critical)")
