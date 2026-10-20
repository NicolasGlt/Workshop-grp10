from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
ARTIFACT_DIR = ROOT / "artifacts"
MODEL_PATH = ARTIFACT_DIR / "model.joblib"
CALIBRATION_PATH = ARTIFACT_DIR / "calibration.json"
SEED = 42
TRAIN_NORMAL_WINDOWS = 6000
CALIBRATION_NORMAL_WINDOWS = 1500
TEST_WINDOWS_PER_SCENARIO = 350
N_ESTIMATORS = 500
# On calibre sur le normal : environ 1 % des fenêtres normales peuvent dépasser le seuil.
FALSE_POSITIVE_QUANTILE = 0.01
