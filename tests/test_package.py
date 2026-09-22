def test_package_exposes_a_version():
    import sluicer

    assert sluicer.__version__.count(".") == 2


def test_the_types_users_touch_are_exported_from_the_package_root():
    import sluicer
    from sluicer.declared.merge import Field, Record

    assert sluicer.Record is Record
    assert sluicer.Field is Field
    assert set(sluicer.__all__) >= {"Extraction", "Field", "Record", "extract"}
