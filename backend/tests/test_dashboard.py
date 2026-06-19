"""DashboardService — metrics, trend, calibration view, history filters. No network."""

from app.services import CalibrationService, DashboardService

from tests.test_calibration import _seed_graded


async def test_metrics_empty(session) -> None:
    m = await DashboardService(session).metrics()
    assert m.n_graded == 0
    assert m.trend == []


async def test_metrics_aggregate_and_trend(session) -> None:
    # 6 matches: predicted 2-1 (home win), all finished 1-1 (draw).
    for i in range(6):
        await _seed_graded(session, f"d{i}", (2, 1), (1, 1))
    await session.commit()

    m = await DashboardService(session).metrics()
    assert m.n_graded == 6
    assert m.outcome_accuracy == 0.0  # predicted win, actual draw
    assert m.exact_rate == 0.0
    assert m.goals_mae == 1.0  # |3 - 2|
    # Trend accumulates over matchdays; last point covers all 6.
    assert m.trend[-1].n == 6
    assert m.trend[-1].cumulative_outcome == 0.0


async def test_calibration_view(session) -> None:
    for i in range(6):
        await _seed_graded(session, f"d{i}", (2, 1), (1, 1))
    await session.commit()
    await CalibrationService(session).recompute()
    await session.commit()

    view = await DashboardService(session).calibration()
    assert view.current is not None and view.current.version == 1
    assert view.prompt_snippet
    # All predictions had confidence 0.5 -> one populated reliability bin at 0% accuracy.
    assert any(b.accuracy == 0.0 and b.n == 6 for b in view.reliability)
    assert view.first_half_brier is not None and view.second_half_brier is not None


async def test_history_filters(session) -> None:
    await _seed_graded(session, "h1", (2, 1), (2, 1))  # exact hit, outcome correct
    await _seed_graded(session, "h2", (2, 1), (0, 3))  # miss
    await session.commit()

    svc = DashboardService(session)
    all_rows = await svc.history(stage=None, outcome=None, limit=100)
    assert len(all_rows) == 2

    hits = await svc.history(stage=None, outcome="hit", limit=100)
    assert len(hits) == 1 and hits[0].exact_hit is True
    assert hits[0].predicted == "2-1" and hits[0].actual == "2-1"

    misses = await svc.history(stage=None, outcome="miss", limit=100)
    assert len(misses) == 1 and misses[0].outcome_correct is False
