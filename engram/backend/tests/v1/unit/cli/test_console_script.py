import tomllib


def test_pyproject_exposes_engram_console_script() -> None:
    with open("pyproject.toml", "rb") as file:
        pyproject = tomllib.load(file)

    assert pyproject["project"]["scripts"]["engram"] == "engram.backend.app.cli.main:main"
