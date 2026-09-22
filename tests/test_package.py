def test_package_exposes_a_version():
    import sluicer

    assert sluicer.__version__.count(".") == 2
