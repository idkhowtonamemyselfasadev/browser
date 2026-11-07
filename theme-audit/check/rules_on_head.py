"""test_sitetheme_rules.py run against git HEAD's theme_web.py, to prove
the checks were red before the fixes."""
import importlib.util, sys, runpy
from pathlib import Path
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("theme_web", HERE / "theme_web.head.py")
mod = importlib.util.module_from_spec(spec)
sys.modules["theme_web"] = mod
spec.loader.exec_module(mod)
sys.argv = [str(HERE.parents[1] / "test_sitetheme_rules.py")]
runpy.run_path(sys.argv[0], run_name="__main__")
