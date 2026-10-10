
# Collect all environment details we CAN determine right now
import sys, platform, torch, torchvision, sklearn, matplotlib
import numpy as np, pandas as pd, scipy, seaborn, tabulate, tqdm
import datetime

info = {}
info['timestamp'] = datetime.datetime.utcnow().isoformat() + "Z"
info['python_version'] = sys.version
info['platform'] = platform.platform()
info['torch_version'] = torch.__version__
info['cuda_build_version'] = torch.version.cuda          # e.g. "13.0"
info['cudnn_version'] = str(torch.backends.cudnn.version())
info['torchvision_version'] = torchvision.__version__
info['sklearn_version'] = sklearn.__version__
info['matplotlib_version'] = matplotlib.__version__
info['numpy_version'] = np.__version__
info['pandas_version'] = pd.__version__
info['scipy_version'] = scipy.__version__
info['seaborn_version'] = seaborn.__version__
info['tabulate_version'] = tabulate.__version__
info['tqdm_version'] = tqdm.__version__

for k, v in info.items():
    print(f"{k}: {v}")
