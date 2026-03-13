import pandas as pd
import numpy as np

idx = pd.bdate_range('2024-01-01', periods=5)
df = pd.DataFrame({'A': [1,2,np.nan,4,5], 'B': [np.nan, 2, 3, np.nan, 5]}, index=idx)
print("Before:")
print(df)
df = df.ffill()
print("\nAfter:")
print(df)
