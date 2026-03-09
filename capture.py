import mss
import numpy as np

sct = mss.mss()

def capture(region):
    img = np.array(sct.grab(region))
    return img
