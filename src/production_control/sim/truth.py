"""Ground truth of the virtual plant: true work times and test outcomes.

The production-control system never sees these values. It only receives
WorkEvents and worker estimates, exactly as it would from a real shop floor.

Every random draw is keyed by ``(seed, unit_operation_id, attempt_no, purpose)``
instead of being taken from a shared random stream. A given operation attempt
therefore has the same true duration and the same test result under every
replanning policy, no matter in which order the policies execute the work
(common random numbers). Policy comparisons are paired, not luck-driven.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from hashlib import blake2b
from math import exp
from statistics import NormalDist

_STANDARD_NORMAL = NormalDist()


def keyed_uniform(seed: int, *key: object) -> float:
    """Return a deterministic U(0, 1) draw for one key, never exactly 0 or 1."""

    digest = blake2b(
        "\x1f".join((str(seed), *map(str, key))).encode("utf-8"),
        digest_size=8,
    ).digest()
    value = int.from_bytes(digest, "big")
    return (value + 0.5) / 2**64


def keyed_standard_normal(seed: int, *key: object) -> float:
    return _STANDARD_NORMAL.inv_cdf(keyed_uniform(seed, *key))


@dataclass(frozen=True, slots=True)
class TruthModel:
    """Parameters of the plant's hidden reality.

    - ``duration_sigma``: log-normal spread of true / standard work time. The
      multiplier is mean-preserving (E = 1), so standard times are unbiased on
      average but individual Units vary. 0 makes every attempt take exactly its
      standard time.
    - ``final_test_fail_probability``: chance that one FINAL_TEST attempt fails
      and sends the Unit back through tuning rework and retest.
    - ``extra_minutes``: injected disturbances, keyed by
      ``(unit_operation_id, attempt_no)``, added on top of the sampled time.
    - ``estimate_sigma``: log-normal error of a worker's expected-remaining
      estimate. 0 means workers estimate the true remaining time exactly.
    - ``duration_multiplier``: systematic slowdown (> 1) of every true work
      time relative to the standard, applied on top of the random spread.
    - ``stoppage_probability`` / ``stoppage_minutes``: chance that an attempt
      is stopped mid-work (material, equipment) and needs ``stoppage_minutes``
      more working time before it finishes. This is a *delay model*: the
      operation stays RUNNING and keeps its resources; no HOLD / RESUME events
      are sent. The system notices it only as a Pace overrun and through the
      worker's expected-remaining answer. HOLD / RESUME event handling is
      tested separately with the API, not in these experiments.
    """

    seed: int = 0
    duration_sigma: float = 0.0
    final_test_fail_probability: float = 0.0
    extra_minutes: Mapping[tuple[str, int], float] = field(default_factory=dict)
    estimate_sigma: float = 0.0
    duration_multiplier: float = 1.0
    stoppage_probability: float = 0.0
    stoppage_minutes: float = 0.0

    def __post_init__(self) -> None:
        if self.duration_sigma < 0:
            raise ValueError("duration_sigma must be 0 or greater")
        if not 0 <= self.final_test_fail_probability < 1:
            raise ValueError("final_test_fail_probability must be in [0, 1)")
        if self.estimate_sigma < 0:
            raise ValueError("estimate_sigma must be 0 or greater")
        if self.duration_multiplier <= 0:
            raise ValueError("duration_multiplier must be greater than 0")
        if not 0 <= self.stoppage_probability < 1:
            raise ValueError("stoppage_probability must be in [0, 1)")
        if self.stoppage_minutes < 0:
            raise ValueError("stoppage_minutes must be 0 or greater")
        for key, minutes in self.extra_minutes.items():
            if minutes < 0:
                raise ValueError(f"extra_minutes must be 0 or greater: {key}")

    def true_minutes(
        self,
        *,
        unit_operation_id: str,
        attempt_no: int,
        standard_minutes: float,
    ) -> float:
        """True active work minutes of one attempt, rounded to whole minutes."""

        if standard_minutes <= 0:
            raise ValueError("standard_minutes must be greater than 0")
        multiplier = 1.0
        if self.duration_sigma > 0:
            z = keyed_standard_normal(self.seed, unit_operation_id, attempt_no, "duration")
            sigma = self.duration_sigma
            multiplier = exp(sigma * z - sigma * sigma / 2)
        sampled = max(1, round(standard_minutes * self.duration_multiplier * multiplier))
        extra = self.extra_minutes.get((unit_operation_id, attempt_no), 0.0)
        # The draw key stays "hold" so results recorded before the rename are
        # reproduced exactly.
        if self.stoppage_probability > 0 and (
            keyed_uniform(self.seed, unit_operation_id, attempt_no, "hold")
            < self.stoppage_probability
        ):
            extra += self.stoppage_minutes
        return float(sampled + round(extra))

    def final_test_passes(self, *, unit_operation_id: str, attempt_no: int) -> bool:
        if self.final_test_fail_probability == 0:
            return True
        draw = keyed_uniform(self.seed, unit_operation_id, attempt_no, "final-test")
        return draw >= self.final_test_fail_probability

    def worker_estimate(
        self,
        *,
        unit_operation_id: str,
        attempt_no: int,
        true_remaining_minutes: float,
        estimate_round: int,
    ) -> float:
        """A worker's expected-remaining answer for a Pace-overrun operation.

        ``estimate_round`` distinguishes repeated questions about the same
        attempt so each answer gets its own error draw.
        """

        if true_remaining_minutes <= 0:
            return 1.0
        multiplier = 1.0
        if self.estimate_sigma > 0:
            z = keyed_standard_normal(
                self.seed, unit_operation_id, attempt_no, "estimate", estimate_round
            )
            multiplier = exp(self.estimate_sigma * z)
        return float(max(1, round(true_remaining_minutes * multiplier)))
