from translaterany.config.loader import load_config
from translaterany.config.model import AppConfig, TranslationConfig


def test_translation_config_defaults():
    cfg = TranslationConfig()
    assert cfg.honorifics == "keep"
    assert cfg.profanity == "faithful"


def test_translation_config_in_app_config():
    app_cfg = AppConfig()
    assert hasattr(app_cfg, "translation")
    assert app_cfg.translation.honorifics == "keep"
    assert app_cfg.translation.profanity == "faithful"


def test_load_config_with_translation_section(tmp_path):
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(
        """
[translation]
honorifics = "adapt"
profanity = "soften"
""",
        encoding="utf-8",
    )
    resolved = load_config(cfg_file)
    assert resolved.app.translation.honorifics == "adapt"
    assert resolved.app.translation.profanity == "soften"
