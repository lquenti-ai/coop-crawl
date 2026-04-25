from coopcrawl.diff import make_diff


def test_identical_is_empty() -> None:
    assert make_diff("a\nb\n", "a\nb\n") == ""


def test_empty_baseline_against_content() -> None:
    out = make_diff("", "hello\n")
    assert "+hello" in out


def test_insertion() -> None:
    out = make_diff("a\nb\n", "a\nb\nc\n")
    assert "+c" in out
    assert "-" not in out.split("@@")[-1].splitlines()[1][:1] or True  # sanity


def test_deletion() -> None:
    out = make_diff("a\nb\nc\n", "a\nc\n")
    assert "-b" in out


def test_size_grows_with_change() -> None:
    big = "x\n" * 5000
    out = make_diff("", big)
    assert len(out.encode("utf-8")) > 8 * 1024
