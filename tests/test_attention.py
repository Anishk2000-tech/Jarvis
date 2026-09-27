from core import attention as a


def test_name_detection_handles_asr_spellings():
    for t in ["Jarvis, open notepad", "hey jarvis what's up", "ok Jervis turn off the lights",
              "जार्विस लाइट बंद करो", "Jarvis's calendar"]:
        assert a.addressed_by_name(t, "JARVIS"), t
    assert not a.addressed_by_name("we should buy a new car", "JARVIS")
    assert a.addressed_by_name("Friday, lights off", "Friday")
    assert a.addressed_by_name("computer do it", "JARVIS", aliases=["computer"])


def test_strip_name():
    assert a.strip_name("Hey Jarvis, open notepad", "Jarvis") == "open notepad"
    assert a.strip_name("Jarvis", "Jarvis") == "Jarvis"


def test_echo_fraction_separates_echo_from_new_voice():
    spoken = ["The weather in Mumbai is thirty two degrees with light rain this evening."]
    assert a.echo_fraction("weather in Mumbai is thirty two degrees", spoken) > 0.9
    assert a.echo_fraction("wait what about tomorrow in Delhi", spoken) < 0.5
    assert a.echo_fraction("anything", []) == 0.0


def test_stop_and_confirm():
    assert a.is_stop_command("stop") and a.is_stop_command("Jarvis wait") and a.is_stop_command("bas")
    assert not a.is_stop_command("please stop the music player on the other computer now thanks")
    assert a.confirm_answer("yes do it") is True
    assert a.confirm_answer("confirm") is True
    assert a.confirm_answer("haan ji") is True
    assert a.confirm_answer("no, cancel that") is False
    assert a.confirm_answer("don't") is False
    assert a.confirm_answer("what is the time in london today please tell me") is None
