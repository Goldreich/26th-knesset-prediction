"""Check a fresh fit against the issued snapshot, without changing the snapshot."""
import json
from pathlib import Path

import numpy as np


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


draws = np.load("generated/joint_draws.npz")
issued = read("site/data/joint_seats.json")
assert list(draws["list_ids"]) == issued["list_ids"]
np.testing.assert_array_equal(draws["seat_draws"], issued["seat_draws"])
np.testing.assert_allclose(draws["vote_draws"].sum(axis=1), 1, atol=1e-12)

fitted = read("generated/terminal_posterior.json")
frozen = read("data/terminal_posterior.json")
assert fitted["list_ids"] == frozen["list_ids"]
for key in ("weights", "means", "covariances"):
    np.testing.assert_allclose(fitted[key], frozen[key], rtol=1e-8, atol=1e-10)
print("All 4,000 seat vectors match; terminal mixture and vote conservation verified.")
