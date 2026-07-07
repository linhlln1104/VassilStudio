from vvoice.core.brand import prepare_spoken_brand_text


def test_spoken_brand_text_separates_display_name_for_tts() -> None:
    assert prepare_spoken_brand_text("Welcome to VassilStudio.") == "Welcome to Vassil Studio."
