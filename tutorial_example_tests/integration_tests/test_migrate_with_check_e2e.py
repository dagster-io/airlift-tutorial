import contextlib
import time
from pathlib import Path
from typing import AbstractSet, Callable, Iterable

import pytest
from dagster import DagsterInstance
from dagster._core.definitions.asset_key import AssetCheckKey, AssetKey
from dagster._core.storage.asset_check_execution_record import AssetCheckExecutionRecordStatus
from dagster._core.storage.dagster_run import DagsterRunStatus

from .utils import start_run_and_wait_for_completion


@pytest.fixture(name="dagster_defs_path")
def setup_dagster_defs_path(
    makefile_dir: Path,
    airflow_instance: None,
    mark_tasks_migrated: Callable[[AbstractSet[str]], contextlib.AbstractContextManager],
) -> Iterable[str]:
    # Mark only the build_dbt_models task as migrated
    with mark_tasks_migrated({"build_dbt_models"}):
        yield str(
            makefile_dir / "tutorial_example" / "dagster_defs" / "stages" / "migrate_with_check.py"
        )


def test_migrate_runs_properly_in_dagster_with_check(
    airflow_instance: None, dagster_dev: None
) -> None:
    instance = DagsterInstance.get()

    from tutorial_example.dagster_defs.stages.migrate_with_check import defs

    all_keys = [spec.key for spec in defs.get_all_asset_specs()]
    assert len(all_keys) == 10

    mat_events = instance.get_latest_materialization_events(asset_keys=all_keys)
    for key, event in mat_events.items():
        assert event is None, f"Materialization event for {key} is not None"

    start_run_and_wait_for_completion("rebuild_customers_list")

    time.sleep(10)

    mat_events = instance.get_latest_materialization_events(asset_keys=all_keys)
    for key, event in mat_events.items():
        assert event is not None, f"Materialization event for {key} is None"

    # Ensure migrated tasks are run in Dagster and check runs even though the task is not migrated
    runs = instance.get_runs()
    assert len(runs) == 2

    dbt_run = runs[1]
    assert dbt_run.asset_selection and len(dbt_run.asset_selection) == 7
    assert dbt_run.status == DagsterRunStatus.SUCCESS

    check_run = runs[0]
    assert check_run.status == DagsterRunStatus.SUCCESS

    assert (
        instance.get_latest_asset_check_evaluation_record(
            AssetCheckKey(asset_key=AssetKey(["customers_csv"]), name="validate_exported_csv")
        ).status  # type: ignore
        == AssetCheckExecutionRecordStatus.SUCCEEDED
    )
