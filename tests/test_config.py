from tapir.config import Config, load, save


def test_missing_file_gives_defaults(tmp_path):
    assert load(tmp_path / "nope.toml") == Config()


def test_round_trip(tmp_path):
    path = tmp_path / "sub" / "config.toml"
    config = Config(
        hours=1, minutes=2, seconds=3, milliseconds=4, button="middle", double_click=True,
        repeat_forever=False, repeat_count=42, start_delay_s=7, hotkey="SUPER+F8",
    )
    save(config, path)
    assert load(path) == config
    assert not path.with_suffix(".tmp").exists()


def test_invalid_values_fall_back_to_defaults(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('seconds = 5\nminutes = "two"\ndouble_click = 1\nbutton = "side"\nunknown = true\n')
    assert load(path) == Config(seconds=5)


def test_corrupt_file_gives_defaults(tmp_path):
    path = tmp_path / "config.toml"
    path.write_bytes(b"seconds = = \xff")
    assert load(path) == Config()
