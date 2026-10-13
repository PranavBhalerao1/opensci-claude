
import pathlib
pathlib.Path('figures').mkdir(exist_ok=True)
pathlib.Path('scripts').mkdir(exist_ok=True)
print("figures/ dir ready:", pathlib.Path('figures').exists())
