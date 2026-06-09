from __future__ import annotations


def test_package_exposes_version():
    import rdc_auto

    assert isinstance(rdc_auto.__version__, str)
    assert rdc_auto.__version__
