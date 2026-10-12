import numpy as np
import pandas as pd

Day = 2

AR_DATA = np.array([-0.038009, -0.038068, -0.038224, -0.038039, -0.035736, -0.038986])
V_Data = np.array([20027000000, 20592000000, 19235000000, 18114000000, 17037000000, 16610000000])

Trade_Volume = 100000000
Trade_Price = 0.01

Averagerate = (AR_DATA[Day-1]*V_Data[Day-1] + Trade_Volume*Trade_Price) / (V_Data[Day])
print(Averagerate)
