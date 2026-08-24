#!/usr/bin/env python3
"""Real-time version of ``profitcontrolsimulator16.py``.

The original model is kept in ``SimulationState.step``.  One call to
``step()`` computes exactly one cycle and returns a small snapshot for a UI.
The command-line program uses that interface to update a Matplotlib window
while the simulation is still running.

Examples:
    python profit_control_realtime.py
    python profit_control_realtime.py --lowerbounds 0 --upperbounds 0.03 \
        --runclients 20 --cycles 1000 --controlrate 25
    python profit_control_realtime.py --no-show --seed 7
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np


DEFAULT_CANDIDATE_COUNT = 100
INTERVAL = 30
ENHANCED = 2
UL = -0.05
HUL = -8.0
DRIFT_BOUNDS = (0.0, 0.0)


def expand_bound(value: str | float | Iterable[float], count: int) -> np.ndarray:
    """Convert one value or a comma-separated list into a per-client array."""
    if isinstance(value, str):
        raw = [part.strip() for part in value.replace(";", ",").split(",")]
        values = [float(part) for part in raw if part]
    else:
        values = [float(item) for item in value] if not np.isscalar(value) else [float(value)]
    if not values:
        raise ValueError("A bound must contain at least one number")
    if len(values) == 1:
        return np.full(count, values[0], dtype=float)
    if len(values) != count:
        raise ValueError(f"Expected one bound or exactly {count} values; got {len(values)}")
    return np.asarray(values, dtype=float)


def take(n: int, iterable: Iterable[Any]) -> list[Any]:
    """Return the first n items of an iterable."""
    result: list[Any] = []
    for item in iterable:
        if len(result) >= n:
            break
        result.append(item)
    return result


def around_poles(cycle: int, poles: list[int], interval: int = INTERVAL) -> bool:
    return any(cycle < pole + interval / 2 and cycle > pole - interval / 2 for pole in poles)


def average_squared_sum(values: list[float] | np.ndarray, center: float) -> float:
    if len(values) == 0:
        return 0.0
    return float(sum((item - center) ** 2 for item in values) / len(values))


def target_function(values: list[float]) -> float:
    """The original three-cluster target heuristic, with safe small-input fallbacks."""
    if len(values) > 50:
        values = values[-50:]
    if len(values) < 3:
        return float(np.mean(values)) if values else 0.0
    ordered = sorted(values)
    maximum = ordered[-1]
    minimum = ordered[0]
    middle_values = ordered.copy()
    middle_values.remove(maximum)
    middle_values.remove(minimum)
    target: dict[tuple[int, int], float] = {}
    average = sum(values) / len(values)
    for i in range(len(middle_values) - 2):
        for j in range(1, len(middle_values) - i - 1):
            target[(i, j)] = (
                average_squared_sum(middle_values[: i + 1], minimum)
                + average_squared_sum(middle_values[i + 1 : i + j + 1], average)
                + average_squared_sum(middle_values[i + j + 1 :], maximum)
            )
    if not target:
        return float(np.mean(values))
    index = min(target, key=target.get)
    lower_half = middle_values[: index[0] + 1] + [minimum]
    middle = middle_values[index[0] + 1 : index[0] + index[1] + 1]
    higher_half = middle_values[index[0] + index[1] + 1 :] + [maximum]
    groups = [lower_half, middle, higher_half]
    largest = max(groups, key=len)
    return float(np.mean(largest))


def target_function_beta(values: list[int]) -> float:
    """The original two-cluster target heuristic, safe for equal-valued input."""
    if len(values) < 3:
        return float(np.mean(values)) if values else 0.0
    ordered = sorted(values)
    maximum = ordered[-1]
    minimum = ordered[0]
    middle_values = ordered.copy()
    middle_values.remove(maximum)
    middle_values.remove(minimum)
    target: dict[int, float] = {}
    for i in range(len(middle_values) - 1):
        target[i] = average_squared_sum(middle_values[: i + 1], minimum) + average_squared_sum(
            middle_values[i + 1 :], maximum
        )
    if not target:
        return float(np.mean(values))
    index = min(target, key=target.get)
    higher_half = middle_values[index + 1 :]
    return float(np.mean(higher_half)) if higher_half else float(np.mean(values))


@dataclass
class CycleSnapshot:
    cycle: int
    selected_position: int
    controlled: bool
    actual_control_count: int
    global_profitrate: float
    accumulated_global_profitrate: float
    latest_profitrates: list[float]
    latest_bets: list[float]
    accumulated_bets: list[float]
    wanted: list[int]
    unwanted: list[int]
    blacked: list[int]
    considered_candidates: list[int]
    finalist_candidates: list[int]


class SimulationState:
    """Mutable simulation state.  ``step`` advances one cycle only."""

    def __init__(
        self,
        lowerbounds: str | float | Iterable[float] = "0.0",
        upperbounds: str | float | Iterable[float] = "0.03",
        runclients: int = 10,
        candidate_count: int = DEFAULT_CANDIDATE_COUNT,
        cycles: int = 500,
        controlrate: float = 0.0,
        seed: int | None = None,
    ) -> None:
        if runclients < 1:
            raise ValueError("runclients must be at least 1")
        if candidate_count < 1:
            raise ValueError("candidate_count must be at least 1")
        if candidate_count > 1000:
            raise ValueError("candidate_count must be 1000 or less")
        if cycles < 1:
            raise ValueError("cycles must be at least 1")
        if not 0 <= controlrate <= 100:
            raise ValueError("controlrate must be between 0 and 100")
        self.runclients = int(runclients)
        self.candidate_count = int(candidate_count)
        self.cycles = int(cycles)
        self.controlrate = float(controlrate)
        self.lowerbounds = expand_bound(lowerbounds, self.runclients)
        self.upperbounds = expand_bound(upperbounds, self.runclients)
        self.rng = np.random.default_rng(seed)
        self.source = np.arange(self.candidate_count)
        self.cycle_index = 0
        self.actualcontrolcount = 0
        self.collectivebets = [[] for _ in range(self.runclients)]
        self.collectivebonus = [[] for _ in range(self.runclients)]
        self.collectiveCPbets = [[] for _ in range(self.runclients)]
        self.collectiveCPbonus = [[] for _ in range(self.runclients)]
        self.spikeslocation = [[] for _ in range(self.runclients)]
        self.chanceofboom = [0] * 9 + [1]
        self.deviationRounds = [0 for _ in range(self.runclients)]
        self.collectivedriftaway: list[list[float]] = []
        self.driftpullingbackactivated = 1
        self.controledplayerbets = [0.0 for _ in range(self.runclients)]
        self.controledplayerbonus = [0.0 for _ in range(self.runclients)]
        self.accubets = [0.0 for _ in range(self.runclients)]
        self.accubonus = [0.0 for _ in range(self.runclients)]
        self.profitrate = [[] for _ in range(self.runclients)]
        self.CPRTP = [[] for _ in range(self.runclients)]
        self.cpd = self.rng.integers(0, self.cycles, size=self.runclients)
        pole_count = int(self.cycles / INTERVAL * 0.7)
        self.eachclientpoles = [
            sorted(self.rng.choice(np.arange(self.cycles), size=pole_count, replace=False).tolist())
            for _ in range(self.runclients)
        ]

    def rankingsales(self) -> list[int]:
        ranked = sorted(range(self.runclients), key=lambda client: self.accubets[client], reverse=True)
        return ranked[: int(self.runclients / 10)]

    def _make_bets(self, cycle: int, client: int) -> tuple[np.ndarray, np.ndarray]:
        """Generate the normal and controlled-player bets for one client."""
        # The original 100-candidate model samples 43-62 normal positions and
        # 10-99 controlled-player positions.  Scale those densities with the
        # candidate count so small candidate spaces do not become saturated.
        normal_low = max(1, int(np.ceil(self.candidate_count * 0.43)))
        normal_high = max(normal_low, int(np.floor(self.candidate_count * 0.62)))
        betcounts = int(self.rng.integers(normal_low, normal_high + 1))
        betnumbers = self.rng.choice(self.source, size=betcounts, replace=False)
        locatingbets = np.zeros(self.candidate_count, dtype=float)
        level = self.rng.permutation([0, 1])
        thissales = np.arange(1, len(level) + 1) * level
        for index in betnumbers:
            if around_poles(cycle, self.eachclientpoles[client]):
                if self.rng.choice(self.chanceofboom) == 0:
                    locatingbets[index] += self.rng.integers(4, 100) * np.sum(thissales) * round(
                        abs(2 + np.sin((cycle - index - self.cpd[client]) * 2 * np.pi / self.cycles)), 2
                    )
                else:
                    locatingbets[index] += self.rng.integers(4, 10) * 100 * np.sum(thissales) * round(
                        abs(2 + np.sin((cycle - index - self.cpd[client]) * 2 * np.pi / self.cycles)), 2
                    )
            else:
                locatingbets[index] += self.rng.integers(4, 10) * 5 * np.sum(thissales) * round(
                    abs(2 + np.sin((cycle - index - self.cpd[client]) * 2 * np.pi / self.cycles)), 2
                )

        specificbets = np.zeros(self.candidate_count, dtype=float)
        if client in range(self.runclients):
            specific_low = max(1, int(np.ceil(self.candidate_count * 0.10)))
            specific_high = max(specific_low, int(np.floor(self.candidate_count * 0.99)))
            specificbetcounts = int(self.rng.integers(specific_low, specific_high + 1))
            specificbetnumbers = self.rng.choice(self.source, size=specificbetcounts)
            for index in specificbetnumbers:
                # ``thissales`` is deliberately the same level used by the
                # original code immediately above.
                specificbets[index] += self.rng.integers(4, 10) * np.sum(thissales)
        locatingbets += specificbets
        return locatingbets, specificbets

    def step(self) -> CycleSnapshot:
        """Compute one cycle and return data suitable for a live chart."""
        if self.cycle_index >= self.cycles:
            raise StopIteration("Simulation has completed")
        c = self.cycle_index
        wanted = np.zeros(self.candidate_count, dtype=int)
        unwanted = np.zeros(self.candidate_count, dtype=int)
        blacked = np.zeros(self.candidate_count, dtype=int)
        eachclientbets = np.zeros(self.runclients, dtype=float)
        eachclientbonustable = [
            np.zeros(self.candidate_count, dtype=float) for _ in range(self.runclients)
        ]
        eachclientplayerbets = np.zeros(self.runclients, dtype=float)
        eachclientplayerbonustable = [
            np.zeros(self.candidate_count, dtype=float) for _ in range(self.runclients)
        ]
        jumpactivated = False
        voting = np.ones(self.runclients, dtype=int)
        voting[7 : min(9, self.runclients)] = 3

        for j in range(self.runclients):
            locatingbets, specificbets = self._make_bets(c, j)
            if np.sum(locatingbets) == 0:
                continue
            topranks = self.rankingsales()
            if self.accubets[j] != 0:
                if j in topranks and self.profitrate[j] and self.profitrate[j][-1] < self.lowerbounds[j]:
                    voting[j] = int(np.log(self.accubets[j])) + 1
            else:
                voting[j] = 0
            if len(self.collectivebets[j]) > 5:
                bar = target_function(self.collectivebets[j])
                if np.sum(locatingbets) > 2 * bar:
                    jumpactivated = True
                    self.spikeslocation[j].append(c)
                    voting[j] = int(c / len(self.spikeslocation[j])) + 1
            if self.profitrate[j] and self.profitrate[j][-1] < 0:
                self.deviationRounds[j] += 1
            else:
                self.deviationRounds[j] = 0
            if self.collectivedriftaway and self.collectivedriftaway[-1][0] > DRIFT_BOUNDS[0]:
                self.driftpullingbackactivated = 1
            elif self.collectivedriftaway and self.collectivedriftaway[-1][0] < DRIFT_BOUNDS[1]:
                self.driftpullingbackactivated = 0
            if self.driftpullingbackactivated and self.profitrate[j]:
                if self.profitrate[j][-1] < UL and self.deviationRounds[j] != 0:
                    multiplier = int(np.log(self.deviationRounds[j])) + 1
                    if multiplier > voting[j]:
                        voting[j] *= multiplier

            specificsum = float(np.sum(specificbets))
            specificbonus = self.candidate_count * specificbets * 0.98
            if specificsum != 0:
                specific_profit = (
                    self.controledplayerbonus[j] + specificbonus
                ) / (self.controledplayerbets[j] + specificsum)
                blacked += (specific_profit < 1) * voting[j] * ENHANCED
            self.controledplayerbets[j] += specificsum
            self.collectiveCPbets[j].append(specificsum)
            eachclientplayerbets[j] = specificsum
            eachclientplayerbonustable[j] = specificbonus
            eachclientbets[j] = np.sum(locatingbets)
            eachclientbonustable[j] = self.candidate_count * locatingbets * 0.98
            each_number_profitrate = (
                1 - eachclientbonustable[j] / eachclientbets[j]
                if eachclientbets[j] != 0
                else np.zeros(self.candidate_count)
            )
            if c > 0:
                self.accubets[j] += self.collectivebets[j][-1]
                self.accubonus[j] += self.collectivebonus[j][-1]
                if self.accubets[j] != 0:
                    self.profitrate[j].append(1 - self.accubonus[j] / self.accubets[j])
                else:
                    self.profitrate[j].append(0.0)
                self.controledplayerbets[j] += self.collectiveCPbets[j][-1]
                self.controledplayerbonus[j] += self.collectiveCPbonus[j][-1]
                self.CPRTP[j].append(
                    self.controledplayerbonus[j] / self.controledplayerbets[j]
                    if self.controledplayerbets[j] != 0
                    else 0.0
                )
                accumulated_total_bets = self.accubets[j] + eachclientbets[j]
                accumulated_total_bonus = self.accubonus[j] + eachclientbonustable[j]
                accumulated_profitrate = 1 - accumulated_total_bonus / accumulated_total_bets
                current_rate = self.profitrate[j][-1]
                if current_rate < self.lowerbounds[j]:
                    for index in range(self.candidate_count):
                        if current_rate > UL:
                            if each_number_profitrate[index] > self.lowerbounds[j]:
                                wanted[index] += 1
                            elif each_number_profitrate[index] <= HUL or accumulated_profitrate[index] <= current_rate:
                                unwanted[index] += voting[j] * (abs(int(each_number_profitrate[index])) + 1)
                        else:
                            if each_number_profitrate[index] > self.lowerbounds[j]:
                                wanted[index] += voting[j]
                            elif each_number_profitrate[index] <= HUL or accumulated_profitrate[index] <= current_rate:
                                unwanted[index] += voting[j] * (abs(int(each_number_profitrate[index])) + 1)
                elif current_rate > self.upperbounds[j]:
                    for index in range(self.candidate_count):
                        if accumulated_profitrate[index] >= self.lowerbounds[j] and each_number_profitrate[index] < current_rate:
                            wanted[index] += 1
                        elif each_number_profitrate[index] <= HUL or each_number_profitrate[index] <= self.lowerbounds[j]:
                            unwanted[index] += voting[j] * (abs(int(each_number_profitrate[index])) + 1)
                else:
                    for index in range(self.candidate_count):
                        if each_number_profitrate[index] <= UL:
                            unwanted[index] += 1
                        if each_number_profitrate[index] <= HUL:
                            unwanted[index] += voting[j] * (abs(int(each_number_profitrate[index])) + 1)

        grandbets = float(np.sum(eachclientbets))
        grandbonus = float(sum(np.sum(table) for table in eachclientbonustable))
        grandprofitrate = 1 - grandbonus / grandbets if grandbets else 0.0
        accumulated_bets_total = float(np.sum(self.accubets) + grandbets)
        accumulated_bonus_total = float(np.sum(self.accubonus) + grandbonus)
        accgrandprofitrate = (
            1 - accumulated_bonus_total / accumulated_bets_total if accumulated_bets_total else 0.0
        )

        maximum_wanted = int(np.max(wanted))
        maximum_unwanted = int(np.max(unwanted))
        maximum_blacked = int(np.max(blacked))
        pen_layers: dict[int, int] = {}
        initial = int(target_function_beta(sorted(wanted.tolist(), reverse=True)))
        for w in range(initial, maximum_wanted + 1):
            wanted_result = np.flatnonzero(wanted == w).tolist()
            if not wanted_result:
                continue
            unwanted_result: list[int] = []
            final_wanted: list[int] = []
            pen_layers[w] = 0
            for i in range(maximum_unwanted):
                copy_result = wanted_result.copy()
                unwanted_result = np.flatnonzero(unwanted == maximum_unwanted - i).tolist()
                for element in wanted_result:
                    if element in unwanted_result:
                        copy_result.remove(element)
                        if not copy_result:
                            final_wanted = wanted_result.copy()
                            break
                if final_wanted:
                    break
                pen_layers[w] = i
                wanted_result = copy_result.copy()

        if pen_layers:
            squared_sum = {
                key: (maximum_wanted - key) ** 2 + (maximum_unwanted - value) ** 2
                for key, value in pen_layers.items()
            }
            index = min(squared_sum, key=squared_sum.get)
            preprocessing = np.flatnonzero(wanted == index).tolist()
            deep = {
                item: (maximum_unwanted - unwanted[item]) ** 2 + blacked[item] ** 2
                for item in preprocessing
            }
            final_wanted_result = [item for item in preprocessing if deep[item] == max(deep.values())]
        else:
            preprocessing = np.flatnonzero(wanted == maximum_wanted).tolist()
            final_wanted_result = preprocessing.copy()
        if not final_wanted_result:
            preprocessing = list(range(self.candidate_count))
            final_wanted_result = preprocessing.copy()

        roll = bool(jumpactivated and self.rng.random() < 0.3)
        controlled = bool(self.rng.integers(0, 100) < self.controlrate or roll)
        if controlled:
            selected_position = int(self.rng.choice(final_wanted_result))
            self.actualcontrolcount += 1
        else:
            selected_position = int(self.rng.choice(self.source))
        for assign in range(self.runclients):
            self.collectivebonus[assign].append(float(eachclientbonustable[assign][selected_position]))
            self.collectivebets[assign].append(float(eachclientbets[assign]))
            self.controledplayerbonus[assign] += float(eachclientplayerbonustable[assign][selected_position])
            self.collectiveCPbonus[assign].append(float(eachclientplayerbonustable[assign][selected_position]))

        latest_profitrates = [history[-1] if history else 0.0 for history in self.profitrate]
        accumulated_bets = [
            float(self.accubets[j] + self.collectivebets[j][-1]) for j in range(self.runclients)
        ]
        snapshot = CycleSnapshot(
            cycle=c,
            selected_position=selected_position,
            controlled=controlled,
            actual_control_count=self.actualcontrolcount,
            global_profitrate=float(grandprofitrate),
            accumulated_global_profitrate=float(accgrandprofitrate),
            latest_profitrates=latest_profitrates,
            latest_bets=eachclientbets.tolist(),
            accumulated_bets=accumulated_bets,
            wanted=wanted.tolist(),
            unwanted=unwanted.tolist(),
            blacked=blacked.tolist(),
            considered_candidates=preprocessing,
            finalist_candidates=final_wanted_result,
        )
        self.cycle_index += 1
        return snapshot

    def run(self) -> list[CycleSnapshot]:
        """Convenience method for callers that want all snapshots."""
        snapshots = []
        while self.cycle_index < self.cycles:
            snapshots.append(self.step())
        return snapshots


def create_live_plot(state: SimulationState):
    import matplotlib.pyplot as plt

    figure, (rate_axis, bet_axis) = plt.subplots(2, 1, figsize=(14, 9), sharex=True)
    figure.canvas.manager.set_window_title("Profit control real-time simulation")
    lines = []
    for client in range(state.runclients):
        line, = rate_axis.plot([], [], linewidth=1.4, label=f"client {client}")
        lines.append(line)
    rate_axis.axhline(float(np.mean(state.lowerbounds)), color="crimson", linestyle="--", label="lower bound")
    rate_axis.axhline(float(np.mean(state.upperbounds)), color="darkorange", linestyle="--", label="upper bound")
    rate_axis.set_ylabel("Profit rate")
    rate_axis.set_ylim(-0.15, 0.35)
    rate_axis.grid(alpha=0.25)
    rate_axis.legend(loc="upper left", ncol=min(5, state.runclients + 2), fontsize=8)
    bars = bet_axis.bar(np.arange(state.runclients), np.zeros(state.runclients), color="cornflowerblue")
    bet_axis.set_xlabel("Merchant / client")
    bet_axis.set_ylabel("Current bets")
    bet_axis.grid(axis="y", alpha=0.25)
    return figure, rate_axis, bet_axis, lines, bars


def update_live_plot(figure, rate_axis, bet_axis, lines, bars, state: SimulationState, snapshot: CycleSnapshot) -> None:
    import matplotlib.pyplot as plt

    for client, line in enumerate(lines):
        history = state.profitrate[client]
        line.set_data(np.arange(1, len(history) + 1), history)
    rate_axis.set_xlim(0, max(10, state.cycles))
    rate_axis.set_title(
        f"Profit rate unfolding | cycle {snapshot.cycle + 1}/{state.cycles} | "
        f"controlled {snapshot.actual_control_count} ({snapshot.actual_control_count / (snapshot.cycle + 1):.1%})"
    )
    for bar, height in zip(bars, snapshot.latest_bets):
        bar.set_height(height)
    bet_axis.set_ylim(0, max(1.0, max(snapshot.latest_bets) * 1.15))
    bet_axis.set_title(f"Latest bets | selected position = {snapshot.selected_position}")
    figure.tight_layout()
    figure.canvas.draw_idle()
    figure.canvas.flush_events()
    plt.pause(0.001)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lowerbounds", default="0.0", help="one value or comma-separated per-client values")
    parser.add_argument("--upperbounds", default="0.03", help="one value or comma-separated per-client values")
    parser.add_argument("--runclients", type=int, default=10)
    parser.add_argument(
        "--candidate-count",
        type=int,
        default=DEFAULT_CANDIDATE_COUNT,
        help="number of discrete candidate positions (1 to 1000)",
    )
    parser.add_argument("--cycles", type=int, default=500)
    parser.add_argument("--controlrate", type=float, default=0.0, help="0 to 100 percent")
    parser.add_argument("--seed", type=int, default=None, help="optional random seed")
    parser.add_argument("--interval-ms", type=float, default=40.0, help="pause after each drawn cycle")
    parser.add_argument("--draw-every", type=int, default=1, help="draw once every N cycles")
    parser.add_argument("--no-show", action="store_true", help="run without opening a Matplotlib window")
    parser.add_argument("--save-json", type=Path, help="save final simulation summary as JSON")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    state = SimulationState(
        lowerbounds=args.lowerbounds,
        upperbounds=args.upperbounds,
        runclients=args.runclients,
        candidate_count=args.candidate_count,
        cycles=args.cycles,
        controlrate=args.controlrate,
        seed=args.seed,
    )
    figure_parts = None
    if not args.no_show:
        figure_parts = create_live_plot(state)
        figure_parts[0].show()
    started = time.perf_counter()
    last_snapshot: CycleSnapshot | None = None
    while state.cycle_index < state.cycles:
        last_snapshot = state.step()
        should_draw = (
            figure_parts is not None
            and (state.cycle_index % max(1, args.draw_every) == 0 or state.cycle_index == state.cycles)
        )
        if should_draw:
            update_live_plot(*figure_parts, state, last_snapshot)
            if args.interval_ms > 0:
                time.sleep(args.interval_ms / 1000.0)
        if state.cycle_index == 1 or state.cycle_index == state.cycles or state.cycle_index % max(1, state.cycles // 10) == 0:
            print(f"cycle {state.cycle_index}/{state.cycles}")

    if last_snapshot is None:
        return
    elapsed = time.perf_counter() - started
    summary = {
        "cycles": state.cycles,
        "runclients": state.runclients,
        "candidate_count": state.candidate_count,
        "lowerbounds": state.lowerbounds.tolist(),
        "upperbounds": state.upperbounds.tolist(),
        "controlrate": state.controlrate,
        "actual_control_count": state.actualcontrolcount,
        "actual_control_rate": state.actualcontrolcount / state.cycles,
        "elapsed_seconds": elapsed,
        "final_profitrates": [history[-1] if history else 0.0 for history in state.profitrate],
        "final_selected_position": last_snapshot.selected_position,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if args.save_json:
        args.save_json.parent.mkdir(parents=True, exist_ok=True)
        args.save_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    if figure_parts is not None:
        import matplotlib.pyplot as plt

        plt.show(block=True)


if __name__ == "__main__":
    main()
