
# Print full checkpoint_stats with all columns
pd.set_option('display.max_columns', None)
pd.set_option('display.width', 200)
pd.set_option('display.float_format', '{:.6f}'.format)
print(ckpt_stats.to_string())
