def test_package_exposes_a_version():
    import sluicer

    assert sluicer.__version__.count(".") == 2


def test_the_types_users_touch_are_exported_from_the_package_root():
    import sluicer
    from sluicer.declared.merge import Field, Record

    assert sluicer.Record is Record
    assert sluicer.Field is Field
    assert set(sluicer.__all__) >= {"Extraction", "Field", "Record", "extract"}


def test_the_fetch_package_has_a_surface_of_its_own():
    """The plan calls it "the package's fetch surface": it has to be one."""
    import sluicer.fetch as fetch_package
    from sluicer.fetch.ladder import fetch
    from sluicer.fetch.result import Climb, Fetched

    assert fetch_package.fetch is fetch
    assert fetch_package.Fetched is Fetched
    assert fetch_package.Climb is Climb
    assert set(fetch_package.__all__) == {"Climb", "Fetched", "fetch"}


def test_the_rung_type_lives_beside_the_result_it_returns():
    """The adapter must not have to import a type from the orchestrator."""
    import sluicer.fetch.result as result
    import sluicer.fetch.scrapling_rungs as adapter

    assert adapter.Rung is result.Rung
