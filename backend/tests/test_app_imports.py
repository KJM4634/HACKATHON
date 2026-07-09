"""
app.main을 실제로 import하는 테스트가 하나도 없어서, scoring.py의
_CATEGORY_TO_REVENUE_BUCKET을 category_mapping.py로 옮기며 app/grid.py의
참조를 안 고친 실수가 pytest에서는 안 걸리고 실제 서버 기동 시에만
ImportError로 터졌다. 이후 같은 종류의 리팩터링 실수를 막기 위한
최소한의 가드."""


def test_app_module_imports_without_error():
    from app.main import app

    assert app is not None


def test_grid_module_imports_without_error():
    from app import grid

    assert grid is not None
