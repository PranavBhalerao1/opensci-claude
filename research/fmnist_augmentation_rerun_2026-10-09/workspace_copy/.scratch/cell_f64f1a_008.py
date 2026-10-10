
# Verify acceptance checks
with open('analysis/trend_diagnostics.txt') as f:
    text = f.read()

print("=== ACCEPTANCE CHECK VERIFICATION ===")

# 1. non-empty and contains 'rho' or 'Spearman'
check1 = len(text) > 0 and ('rho' in text or 'Spearman' in text)
print(f"[1] Non-empty AND contains 'rho' or 'Spearman': {check1}")

# 2. contains concordance fraction
check2 = 'concordance fraction' in text.lower() or 'Concordance fraction' in text
print(f"[2] Contains concordance fraction: {check2}")

# 3. contains epoch-1 loss comparison result
check3 = 'epoch' in text.lower() and ('loss' in text.lower()) and ('/' in text)
print(f"[3] Contains epoch-1 loss comparison result: {check3}")

print("\n=== FULL FILE ===")
print(text)
