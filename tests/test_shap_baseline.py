import numpy as np
import pytest

pytest.importorskip("shap")

from sklearn.ensemble import HistGradientBoostingClassifier  # noqa: E402

from sbc_vision.perception.baselines.opencv_baseline import (  # noqa: E402
    BACKGROUND,
    DEFAULT_PARAMS,
    FEATURE_NAMES,
    OpenCVBaseline,
)
from sbc_vision.perception.explain.shap_baseline import summarize  # noqa: E402


def test_the_feature_that_decides_the_class_ranks_first_with_its_direction():
    rng = np.random.default_rng(0)
    x = rng.normal(size=(600, len(FEATURE_NAMES)))
    # Une forte densité de texte fait un lien, une faible un bouton, le reste est du bruit.
    text = FEATURE_NAMES.index("text_density")
    y = np.where(x[:, text] > 0.5, "link", np.where(x[:, text] < -0.5, "button", BACKGROUND))
    classifier = HistGradientBoostingClassifier(max_iter=50, random_state=0).fit(x, y)
    model = OpenCVBaseline(classifier, tuple(classifier.classes_), DEFAULT_PARAMS)
    predicted = np.array([model.classes.index(label) for label in classifier.predict(x)])
    summary = summarize(model, x, predicted)
    link, button = summary["link"]["features"][0], summary["button"]["features"][0]
    assert link["feature"] == button["feature"] == "text_density"
    assert link["direction"] > 0.5 and button["direction"] < -0.5
